# -*- coding: utf-8 -*-

from odoo import models, fields


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    stage_scope = fields.Selection(
        [
            ('lead', 'Lead'),
            ('opportunity', 'Opportunity'),
            ('both', 'Both'),
        ],
        string='Show In',
        default='both',
        required=True,
        help='Controls whether this stage appears for leads, opportunities, or both.'
    )

    show_create_loi = fields.Boolean(
        string='Show Create LOI Button',
        default=False,
        help='If checked, the "Create LOI" button will be visible in the CRM opportunity form when this stage is selected.'
    )

    show_view_loi = fields.Boolean(
        string='Show View LOI Button',
        default=False,
        help='If checked, the "View LOI" button will be visible in the CRM opportunity form when this stage is selected.'
    )

    show_generate_installments = fields.Boolean(
        string='Show Generate Installments Button',
        default=False,
        help='If checked, "Generate Installments" is visible on the opportunity when this stage is selected.'
    )

    show_share_unit = fields.Boolean(
        string='Show Share Unit Button',
        default=False,
        help='If checked, the "Share Unit" button will be visible in the CRM opportunity form when this stage is selected.'
    )

