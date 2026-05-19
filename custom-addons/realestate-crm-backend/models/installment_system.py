# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


# Regular payment frequency → installments per year & step (months) between dues
FREQUENCY_PERIODS_PER_YEAR = {
    'monthly': 12,
    'quarterly': 4,
    'semi_annual': 2,
    'annual': 1,
}
INSTALLMENT_STEP_MONTHS = {
    'monthly': 1,
    'quarterly': 3,
    'semi_annual': 6,
    'annual': 12,
}
# Bullet add-on payments per year & month step between bullet dues
BULLET_PERIODS_PER_YEAR = {
    'quarterly': 4,
    'semi_annual': 2,
    'annual': 1,
}
BULLET_STEP_MONTHS = {
    'quarterly': 3,
    'semi_annual': 6,
    'annual': 12,
}


# Generated rows on crm.lead (real.estate.installment.line)
INSTALLMENT_LINE_TYPES = [
    ('down_payment', 'Down Payment'),
    ('booking', 'Booking / Reservation'),
    ('installment', 'Installment'),
    ('milestone', 'Milestone / Bullet'),
    ('handover', 'Handover / Delivery'),
    ('maintenance', 'Maintenance'),
    ('fees', 'Fees / Charges'),
    ('other', 'Other'),
]


class RealEstateInstallmentSystem(models.Model):
    _name = 'real.estate.installment.system'
    _description = 'Installment Template'
    _rec_name = 'name'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Description', required=True)
    active = fields.Boolean(default=True)
    valid_from = fields.Date(string='Valid From')
    valid_to = fields.Date(string='Valid To')

    duration_years = fields.Integer(
        string='Installment duration (years)',
        default=1,
        help='مدة التقسيط بالسنوات.',
    )
    payment_frequency = fields.Selection(
        [
            ('monthly', 'Monthly / شهري'),
            ('quarterly', 'Quarterly / ربع سنوي'),
            ('semi_annual', 'Semi-annual / نصف سنوي'),
            ('annual', 'Annual / سنوي'),
        ],
        string='Installment frequency',
        default='monthly',
        required=True,
        help='تكرار القسط العادي.',
    )
    installments_per_year = fields.Integer(
        string='Installments per year',
        compute='_compute_frequency_derived',
        help='12 / 4 / 2 / 1 حسب التكرار.',
    )
    installment_count = fields.Integer(
        string='Total installments',
        compute='_compute_installment_count',
        help='عدد الأقساط = مدة التقسيط × عدد الأقساط في السنة.',
    )

    dp_type = fields.Selection(
        [('percent', 'Percentage'), ('amount', 'Fixed Amount')],
        string='Down payment type',
        default='percent',
        help='المقدم: نسبة أو مبلغ ثابت.',
    )
    down_payment_percent = fields.Float(string='Down payment %')
    down_payment_amount = fields.Float(string='Down payment amount')

    disc_type = fields.Selection(
        [('percent', 'Percentage'), ('amount', 'Fixed Amount')],
        string='Discount type',
        default='percent',
    )
    discount_percent = fields.Float(string='Discount %')
    discount_amount = fields.Float(string='Discount amount')

    bullet_line_ids = fields.One2many(
        'real.estate.installment.bullet.line',
        'template_id',
        string='Bullet payments',
        help='Extra periodic amounts; total bullets are reserved before splitting regular installments.',
    )

    scope_project_enabled = fields.Boolean(
        string='Template applies to a project',
        help='If set, this template is only offered when the opportunity matches the selected project.',
    )
    scope_project_id = fields.Many2one(
        'real.estate.project',
        string='Project',
        ondelete='set null',
    )
    scope_phase_enabled = fields.Boolean(
        string='Template applies to a phase',
        help='If set, this template is only offered when the opportunity matches the selected phase (sector).',
    )
    scope_phase_id = fields.Many2one(
        'real.estate.sector',
        string='Phase',
        ondelete='set null',
        help='Phase within a project (sector).',
    )

    pen_type = fields.Selection(
        [('percent', 'Percentage'), ('amount', 'Fixed Amount')],
        string='Penalty type',
        default='percent',
    )
    penalty_percent = fields.Float(string='Penalty %')
    penalty_amount = fields.Float(string='Penalty amount')

    grace_period_days = fields.Integer(string='Grace period (days)', default=0)

    @api.onchange('dp_type', 'disc_type', 'pen_type')
    def _onchange_types(self):
        if self.dp_type == 'percent':
            self.down_payment_amount = 0.0
        else:
            self.down_payment_percent = 0.0
        if self.disc_type == 'percent':
            self.discount_amount = 0.0
        else:
            self.discount_percent = 0.0
        if self.pen_type == 'percent':
            self.penalty_amount = 0.0
        else:
            self.penalty_percent = 0.0

    @api.onchange('scope_project_id')
    def _onchange_scope_project_clear_phase(self):
        if (
            self.scope_phase_id
            and self.scope_project_id
            and self.scope_phase_id.project_id != self.scope_project_id
        ):
            self.scope_phase_id = False

    @api.depends('payment_frequency')
    def _compute_frequency_derived(self):
        for rec in self:
            rec.installments_per_year = FREQUENCY_PERIODS_PER_YEAR.get(
                rec.payment_frequency or 'monthly', 12
            )

    @api.depends('duration_years', 'payment_frequency')
    def _compute_installment_count(self):
        for rec in self:
            y = rec.duration_years or 0
            mult = FREQUENCY_PERIODS_PER_YEAR.get(rec.payment_frequency or 'monthly', 12)
            rec.installment_count = y * mult

    @api.constrains('duration_years')
    def _check_template(self):
        for rec in self:
            if (rec.duration_years or 0) <= 0:
                raise ValidationError(_('Installment duration (years) must be positive.'))

    @api.constrains(
        'scope_project_enabled',
        'scope_project_id',
        'scope_phase_enabled',
        'scope_phase_id',
    )
    def _check_scope(self):
        for rec in self:
            if rec.scope_project_enabled and not rec.scope_project_id:
                raise ValidationError(
                    _('Select a project when "Template applies to a project" is enabled.')
                )
            if rec.scope_phase_enabled and not rec.scope_phase_id:
                raise ValidationError(
                    _('Select a phase when "Template applies to a phase" is enabled.')
                )
            if (
                rec.scope_project_enabled
                and rec.scope_project_id
                and rec.scope_phase_enabled
                and rec.scope_phase_id
                and rec.scope_phase_id.project_id != rec.scope_project_id
            ):
                raise ValidationError(
                    _('The selected phase must belong to the selected project.')
                )

    @api.model
    def _cron_archive_expired_systems(self):
        today = fields.Date.today()
        expired = self.search([
            ('active', '=', True),
            ('valid_to', '!=', False),
            ('valid_to', '<', today),
        ])
        if expired:
            expired.write({'active': False})


class RealEstateInstallmentBulletLine(models.Model):
    _name = 'real.estate.installment.bullet.line'
    _description = 'Installment Template Bullet Line'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'real.estate.installment.system',
        string='Template',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Label')
    frequency = fields.Selection(
        [
            ('quarterly', 'Quarterly'),
            ('semi_annual', 'Semi-annual'),
            ('annual', 'Annual'),
        ],
        string='Bullet frequency',
        required=True,
        default='annual',
    )
    value_type = fields.Selection(
        [
            ('percent', '% of amount after discount'),
            ('fixed', 'Fixed amount'),
        ],
        string='Value type',
        required=True,
        default='fixed',
    )
    amount_value = fields.Float(
        string='Amount / %',
        required=True,
        default=0.0,
    )

    @api.constrains('amount_value')
    def _check_amount_value(self):
        for line in self:
            if line.amount_value < 0:
                raise ValidationError(_('Bullet amount / percentage cannot be negative.'))
