# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    real_estate_installment_line_id = fields.Many2one(
        'real.estate.installment.line',
        string='Installment Line',
        ondelete='set null',
        index=True,
    )
    payment_type_custom = fields.Selection(
        [
            ('installment', 'Installment'),
            ('penalty', 'Penalty'),
            ('both', 'Both'),
        ],
        string='Installment Allocation',
        default='both',
    )


class AccountMove(models.Model):
    _inherit = 'account.move'

    invoice_payment_type = fields.Selection(
        [
            ('installment', 'Installment'),
            ('penalty', 'Penalty'),
        ],
        string='Installment Invoice Type',
    )
    real_estate_installment_line_id = fields.Many2one(
        'real.estate.installment.line',
        string='Installment Line',
        ondelete='set null',
        index=True,
    )


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        lines = batch_result.get('lines')
        if lines:
            move = lines[0].move_id
            if move.real_estate_installment_line_id:
                vals['real_estate_installment_line_id'] = (
                    move.real_estate_installment_line_id.id
                )
                vals['payment_type_custom'] = move.invoice_payment_type or 'installment'
        return vals
