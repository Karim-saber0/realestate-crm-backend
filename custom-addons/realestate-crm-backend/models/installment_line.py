# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .installment_system import INSTALLMENT_LINE_TYPES


class RealEstateInstallmentLine(models.Model):
    _name = 'real.estate.installment.line'
    _description = 'Real Estate Installment Line'
    _order = 'installment_no asc'

    lead_id = fields.Many2one(
        'crm.lead',
        string='Opportunity',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='lead_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='lead_id.currency_id',
        store=True,
    )

    installment_no = fields.Integer(string='Installment #', required=True, readonly=True)
    installment_type = fields.Selection(
        INSTALLMENT_LINE_TYPES,
        string='Installment Type',
    )
    due_date = fields.Date(string='Due Date', required=True)
    amount = fields.Float(
        string='Amount',
        currency_field='currency_id',
        required=True,
    )
    discount_amount = fields.Float(
        string='Discount',
        currency_field='currency_id',
        default=0.0,
    )

    penalty_rate = fields.Float(string='Penalty Rate %')  # daily base when percent
    penalty_amount_fixed = fields.Float(string='Fixed Penalty')  # when not percent
    grace_days = fields.Integer(string='Grace Days', default=0)

    remaining_installment = fields.Float(
        string='Remaining Installment',
        currency_field='currency_id',
        compute='_compute_financials',
        store=True,
    )
    remaining_penalty = fields.Float(
        string='Remaining Penalty',
        currency_field='currency_id',
        compute='_compute_financials',
        store=True,
    )
    penalty_value = fields.Float(
        string='Accumulated Penalty',
        compute='_compute_financials',
        store=True,
    )

    paid_installment = fields.Float(
        string='Paid (Installment)',
        currency_field='currency_id',
        compute='_compute_payments',
        store=True,
    )
    paid_penalty = fields.Float(
        string='Paid (Penalty)',
        currency_field='currency_id',
        compute='_compute_payments',
        store=True,
    )
    amount_paid = fields.Float(
        string='Total Paid',
        currency_field='currency_id',
        compute='_compute_payments',
        store=True,
    )

    total_required = fields.Float(
        string='Total Required',
        currency_field='currency_id',
        compute='_compute_financials',
        store=True,
    )
    total_payable = fields.Float(
        string='Total Payable',
        currency_field='currency_id',
        compute='_compute_financials',
        store=True,
    )

    status = fields.Selection(
        [
            ('upcoming', 'Upcoming'),
            ('partial', 'Partial'),
            ('paid', 'Paid'),
            ('late', 'Late'),
            ('legal', 'Legal'),
        ],
        compute='_compute_status',
        store=True,
    )

    payment_ids = fields.One2many(
        'account.payment',
        'real_estate_installment_line_id',
        string='Payments',
    )
    invoice_ids = fields.One2many(
        'account.move',
        'real_estate_installment_line_id',
        string='Invoices',
    )
    overdue_notice_sent = fields.Boolean(
        string='Overdue chatter notice sent',
        default=False,
        help='Set when the overdue reminder cron posted on the opportunity.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('installment_no') and vals.get('lead_id'):
                last = self.search(
                    [('lead_id', '=', vals['lead_id'])],
                    order='installment_no desc',
                    limit=1,
                )
                vals['installment_no'] = (last.installment_no + 1) if last else 1
        return super().create(vals_list)

    @api.depends(
        'payment_ids.amount',
        'payment_ids.state',
        'payment_ids.payment_type_custom',
    )
    def _compute_payments(self):
        for rec in self:
            posted = rec.payment_ids.filtered(
                lambda p: p.state in ('in_process', 'paid')
            )
            p_inst = sum(
                p.amount for p in posted if p.payment_type_custom == 'installment'
            )
            p_pen = sum(p.amount for p in posted if p.payment_type_custom == 'penalty')
            p_both = sum(p.amount for p in posted if p.payment_type_custom == 'both')
            rec.paid_installment = p_inst + p_both
            rec.paid_penalty = p_pen
            rec.amount_paid = rec.paid_installment + rec.paid_penalty

    @api.depends(
        'due_date',
        'amount',
        'grace_days',
        'penalty_rate',
        'penalty_amount_fixed',
        'paid_penalty',
        'paid_installment',
        'currency_id',
    )
    def _compute_financials(self):
        today = fields.Date.today()
        for rec in self:
            penalty_accumulated = 0.0
            if rec.due_date:
                delay = (today - rec.due_date).days
                if delay > (rec.grace_days or 0):
                    overdue_days = delay - (rec.grace_days or 0)
                    if rec.penalty_rate and rec.penalty_rate > 0:
                        p_base = (rec.penalty_rate / 100.0) * rec.amount
                    else:
                        p_base = rec.penalty_amount_fixed or 0.0
                    penalty_accumulated = min(
                        p_base * overdue_days,
                        rec.amount or 0.0,
                    )

            rec.penalty_value = penalty_accumulated
            rec.remaining_penalty = max(0.0, penalty_accumulated - (rec.paid_penalty or 0.0))
            rec.remaining_installment = max(
                0.0,
                (rec.amount or 0.0) - (rec.paid_installment or 0.0),
            )
            rec.total_required = rec.remaining_installment + rec.remaining_penalty
            rec.total_payable = rec.total_required

    @api.depends(
        'total_payable',
        'amount_paid',
        'due_date',
        'amount',
        'penalty_value',
    )
    def _compute_status(self):
        today = fields.Date.today()
        for rec in self:
            if rec.total_payable <= 0 and (
                (rec.amount or 0) > 0 or (rec.penalty_value or 0) > 0
            ):
                rec.status = 'paid'
            elif rec.amount_paid > 0:
                rec.status = 'partial'
            elif (rec.penalty_value or 0) >= (rec.amount or 0) and (rec.amount or 0) > 0:
                rec.status = 'legal'
            elif rec.due_date and rec.due_date < today:
                rec.status = 'late'
            else:
                rec.status = 'upcoming'

    def _default_sale_line_account(self):
        journal = self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', self.env.company.id)],
            limit=1,
        )
        return journal.default_account_id.id if journal else False

    def _create_invoice(self, amount, label, payment_type_key):
        self.ensure_one()
        if amount <= 0:
            raise UserError(_('Amount must be positive.'))
        partner = self.lead_id.partner_id
        if not partner:
            raise UserError(_('Set a customer on the opportunity first.'))
        account_id = self._default_sale_line_account()
        line_vals = {'name': label, 'quantity': 1.0, 'price_unit': amount}
        if account_id:
            line_vals['account_id'] = account_id
        company = self.company_id or self.env.company
        move = (
            self.env['account.move']
            .with_company(company)
            .create(
                {
                    'move_type': 'out_invoice',
                    'company_id': company.id,
                    'partner_id': partner.id,
                    'invoice_date': fields.Date.today(),
                    'real_estate_installment_line_id': self.id,
                    'invoice_payment_type': payment_type_key,
                    'invoice_line_ids': [(0, 0, line_vals)],
                }
            )
        )
        return move

    def action_invoice_penalty(self):
        self.ensure_one()
        remaining_pen = self.remaining_penalty
        if remaining_pen <= 0:
            raise UserError(_('No penalty due.'))
        move = self._create_invoice(
            remaining_pen,
            _('Late penalty — installment #%s') % self.installment_no,
            'penalty',
        )
        return self._open_invoice(move)

    def action_invoice_installment(self):
        self.ensure_one()
        remaining_inst = self.remaining_installment
        if remaining_inst <= 0:
            raise UserError(_('Installment principal is fully paid.'))
        move = self._create_invoice(
            remaining_inst,
            _('Installment #%s') % self.installment_no,
            'installment',
        )
        return self._open_invoice(move)

    def _open_invoice(self, move):
        return {
            'name': _('Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'context': {'default_move_type': 'out_invoice'},
        }

    def action_pay_installment_partial(self):
        self.ensure_one()
        return self._open_pay_wizard(self.remaining_installment, 'installment')

    def action_pay_penalty_partial(self):
        self.ensure_one()
        return self._open_pay_wizard(self.remaining_penalty, 'penalty')

    def action_pay_all(self):
        self.ensure_one()
        if self.remaining_penalty <= 0 and self.remaining_installment <= 0:
            raise UserError(_('Nothing to pay.'))
        return self._open_pay_wizard(self.total_payable, 'both')

    def _open_pay_wizard(self, amount, p_type):
        self.ensure_one()
        if amount <= 0:
            raise UserError(_('Remaining amount is zero.'))
        partner = self.lead_id.partner_id
        journal = self.env['account.journal'].search(
            [
                ('type', 'in', ('bank', 'cash')),
                ('company_id', '=', self.company_id.id or self.env.company.id),
            ],
            limit=1,
        )
        if not journal:
            raise UserError(_('Configure a bank or cash journal for this company.'))
        payment_method_line = journal.inbound_payment_method_line_ids[:1]
        if not payment_method_line:
            raise UserError(_('Configure an inbound payment method on journal %s.') % journal.display_name)

        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': amount,
            'journal_id': journal.id,
            'payment_method_line_id': payment_method_line.id,
            'memo': _('Settlement (%s) installment #%s')
            % (p_type, self.installment_no),
            'real_estate_installment_line_id': self.id,
            'payment_type_custom': p_type,
        })
        return {
            'name': _('Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def cron_auto_invoice_upcoming_installments(self):
        """Optionally create draft customer invoices N days before due date (see Settings)."""
        days_before = int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param('real_estate_crm.installment_invoice_days_before', '0')
        )
        if days_before <= 0:
            return
        horizon = fields.Date.today() + timedelta(days=days_before)
        lines = self.search(
            [
                ('due_date', '<=', horizon),
                ('due_date', '>=', fields.Date.today()),
                ('remaining_installment', '>', 0),
            ]
        )
        for line in lines:
            open_inv = line.invoice_ids.filtered(
                lambda m: m.state in ('draft', 'posted') and m.move_type == 'out_invoice'
            )
            if open_inv:
                continue
            partner = line.lead_id.partner_id
            if not partner or line.remaining_installment <= 0:
                continue
            line._create_invoice(
                line.remaining_installment,
                _('Installment #%s — due %s')
                % (line.installment_no, line.due_date or ''),
                'installment',
            )

    @api.model
    def cron_overdue_installment_chatter_reminder(self):
        """Post one chatter reminder on the opportunity when an installment is late (optional)."""
        days_late = int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param('real_estate_crm.installment_late_alert_after_days', '0')
        )
        if days_late <= 0:
            return
        cutoff = fields.Date.today() - timedelta(days=days_late)
        lines = self.search(
            [
                ('due_date', '<', cutoff),
                ('total_payable', '>', 0),
                ('status', 'in', ('late', 'partial')),
            ],
            limit=500,
        )
        for line in lines:
            if line.overdue_notice_sent:
                continue
            if line.lead_id:
                line.lead_id.message_post(
                    body=_(
                        'Installment #%(no)s is overdue (due %(due)s). Remaining payable: %(amt)s.'
                    )
                    % {
                        'no': line.installment_no,
                        'due': line.due_date or '',
                        'amt': line.total_payable,
                    }
                )
            line.overdue_notice_sent = True
