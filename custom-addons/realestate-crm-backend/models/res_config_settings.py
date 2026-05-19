# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    installment_invoice_days_before = fields.Integer(
        string='Installment invoices (days before due)',
        config_parameter='real_estate_crm.installment_invoice_days_before',
        default=0,
        help='If greater than zero, a daily cron creates draft customer invoices for installment '
        'lines whose due date falls within this many days from today.',
    )
    installment_late_alert_after_days = fields.Integer(
        string='Overdue reminder on opportunity (days late)',
        config_parameter='real_estate_crm.installment_late_alert_after_days',
        default=0,
        help='If greater than zero, a cron posts a chatter message on the opportunity once '
        'per installment line after it is this many days overdue.',
    )
