# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round

from .installment_system import (
    BULLET_PERIODS_PER_YEAR,
    BULLET_STEP_MONTHS,
    FREQUENCY_PERIODS_PER_YEAR,
    INSTALLMENT_STEP_MONTHS,
)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    co_sales_id = fields.Many2one(
        'res.users',
        string='Co Sales',
        help='Secondary salesperson supporting this lead/opportunity'
    )
    customer_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='partner_id',
        store=True,
        readonly=True
    )

    # Real Estate Fields
    project_id = fields.Many2one(
        'real.estate.project',
        string='Project',
        help='Real estate project related to this opportunity'
    )
    sector_id = fields.Many2one(
        'real.estate.sector',
        string='Sector',
        help='Sector within the project'
    )
    building_id = fields.Many2one(
        'real.estate.building',
        string='Building',
        help='Building within the sector'
    )
    unit_id = fields.Many2one(
        'real.estate.unit',
        string='Unit',
        help='Specific unit of interest'
    )
    
    # Unit Details (Auto-populated from unit_id)
    unit_type = fields.Selection([
        ('studio', 'Studio'),
        ('br1', '1 Bedroom'),
        ('br2', '2 Bedrooms'),
        ('br3', '3 Bedrooms'),
        ('br4', '4 Bedrooms'),
        ('br5', '5+ Bedrooms'),
        ('penthouse', 'Penthouse'),
        ('duplex', 'Duplex'),
        ('office', 'Office'),
        ('retail', 'Retail'),
        ('warehouse', 'Warehouse'),
    ], string='Unit Type', related='unit_id.unit_type', store=True)
    
    unit_area_sqft = fields.Float(
        string='Unit Area (Sq Ft)',
        related='unit_id.area_sqft',
        store=True
    )
    unit_price = fields.Monetary(
        string='Unit Price',
        related='unit_id.price',
        store=True,
        currency_field='currency_id'
    )
    unit_bedrooms = fields.Integer(
        string='Bedrooms',
        related='unit_id.bedrooms',
        store=True
    )
    unit_bathrooms = fields.Integer(
        string='Bathrooms',
        related='unit_id.bathrooms',
        store=True
    )
    
    # Geolocation Fields
    agent_latitude = fields.Float(
        string='Agent Latitude',
        digits=(10, 7),
        help='Agent location latitude when opportunity was created'
    )
    agent_longitude = fields.Float(
        string='Agent Longitude',
        digits=(10, 7),
        help='Agent location longitude when opportunity was created'
    )
    
    # Real Estate Specific Fields
    property_type = fields.Selection([
        ('residential', 'Residential'),
        ('commercial', 'Commercial'),
        ('industrial', 'Industrial'),
        ('land', 'Land'),
    ], string='Property Type', default='residential')
    
    # Currency used for monetary fields on the opportunity
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    
    budget_min = fields.Monetary(
        string='Minimum Budget',
        currency_field='currency_id'
    )
    budget_max = fields.Monetary(
        string='Maximum Budget',
        currency_field='currency_id'
    )
    
    preferred_location = fields.Char(
        string='Preferred Location',
        help='Customer preferred location'
    )
    
    move_in_date = fields.Date(
        string='Preferred Move-in Date',
        help='Customer preferred move-in date'
    )
    
    financing_needed = fields.Boolean(
        string='Financing Needed',
        default=False
    )
    
    pre_approved = fields.Boolean(
        string='Pre-approved',
        default=False,
        help='Customer has pre-approved financing'
    )
    
    # LOI
    loi_id = fields.Many2one(
        'real.estate.loi',
        string='Letter of Intent',
        help='Associated Letter of Intent'
    )

    installment_system_id = fields.Many2one(
        'real.estate.installment.system',
        string='Installment System',
        domain="[('active', '=', True)]",
    )
    installment_base_price = fields.Monetary(
        string='Installment base amount',
        currency_field='currency_id',
        related='unit_id.price',
        help='Amount used to build the schedule (defaults from the unit price on the Real Estate tab). '
        'Leave empty or zero to use unit price.',
    )
    installment_start_date = fields.Date(
        string='Installment Start Date',
        default=fields.Date.context_today,
    )
    installment_line_ids = fields.One2many(
        'real.estate.installment.line',
        'lead_id',
        string='Installments',
    )

    # Computed fields for button visibility based on stage settings
    show_create_loi_button = fields.Boolean(
        string='Show Create LOI Button',
        compute='_compute_stage_button_visibility',
        store=False
    )
    
    show_view_loi_button = fields.Boolean(
        string='Show View LOI Button',
        compute='_compute_stage_button_visibility',
        store=False
    )
    
    show_generate_installments_button = fields.Boolean(
        string='Show Generate Installments Button',
        compute='_compute_stage_button_visibility',
        store=False,
    )
    
    show_share_unit_button = fields.Boolean(
        string='Show Share Unit Button',
        compute='_compute_stage_button_visibility',
        store=False
    )

    @api.depends(
        'stage_id',
        'stage_id.show_create_loi',
        'stage_id.show_view_loi',
        'stage_id.show_generate_installments',
        'stage_id.show_share_unit',
    )
    def _compute_stage_button_visibility(self):
        """Compute button visibility based on stage settings"""
        for lead in self:
            stage = lead.stage_id
            lead.show_create_loi_button = stage.show_create_loi if stage else False
            lead.show_view_loi_button = stage.show_view_loi if stage else False
            lead.show_generate_installments_button = (
                stage.show_generate_installments if stage else False
            )
            lead.show_share_unit_button = stage.show_share_unit if stage else False

    @api.onchange('unit_id')
    def _onchange_unit_id(self):
        """Auto-populate project, sector, building when unit is selected"""
        if self.unit_id:
            self.project_id = self.unit_id.project_id
            self.sector_id = self.unit_id.sector_id
            self.building_id = self.unit_id.building_id
            self.unit_price = self.unit_id.price
            self.installment_base_price = self.unit_id.price
            self.currency_id = self.unit_id.currency_id
        else:
            self.installment_base_price = False

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """Clear sector, building, unit when project changes"""
        if not self.project_id:
            self.sector_id = False
            self.building_id = False
            self.unit_id = False

    @api.onchange('sector_id')
    def _onchange_sector_id(self):
        """Clear building, unit when sector changes"""
        if not self.sector_id:
            self.building_id = False
            self.unit_id = False

    @api.onchange('building_id')
    def _onchange_building_id(self):
        """Clear unit when building changes"""
        if not self.building_id:
            self.unit_id = False

    @api.onchange('type')
    def _onchange_type(self):
        for record in self:
            if record.stage_id and not record._is_stage_allowed(record.stage_id):
                record.stage_id = False

    def _is_stage_allowed(self, stage):
        self.ensure_one()
        if not stage:
            return True
        if stage.stage_scope == 'both':
            return True
        lead_type = self.type or 'lead'
        return stage.stage_scope == lead_type

    @api.constrains('stage_id', 'type')
    def _check_stage_scope(self):
        for record in self:
            if record.stage_id and not record._is_stage_allowed(record.stage_id):
                raise ValidationError(
                    _('Selected stage is not allowed for this record type (Lead/Opportunity).')
                )

    def action_create_loi(self):
        """Create Letter of Intent from opportunity"""
        self.ensure_one()
        if not self.unit_id:
            raise UserError(_('Please select a unit before creating a Letter of Intent.'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Letter of Intent'),
            'res_model': 'real.estate.loi',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_opportunity_id': self.id,
                'default_unit_id': self.unit_id.id,
                'default_customer_id': self.partner_id.id,
                'default_price': self.unit_price,
            },
        }

    def action_view_loi(self):
        """View associated Letter of Intent"""
        self.ensure_one()
        if not self.loi_id:
            return self.action_create_loi()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Letter of Intent'),
            'res_model': 'real.estate.loi',
            'res_id': self.loi_id.id,
            'view_mode': 'form',
        }

    def _generate_installment_schedule_from_template(self):
        """Remove existing schedule rows and rebuild from template (relativedelta due dates)."""
        self.ensure_one()
        if self.type != 'opportunity':
            raise UserError(_('Installments can only be generated on opportunities.'))
        if not self.unit_id or not self.installment_system_id:
            raise UserError(_('Please set a unit and an installment template.'))

        base_price = self.installment_base_price or self.unit_price or 0.0
        if base_price <= 0:
            raise UserError(
                _('Set a positive installment base amount or unit price (Real Estate Information).')
            )

        sys = self.installment_system_id
        today = fields.Date.today()
        if sys.valid_from and today < sys.valid_from:
            raise UserError(_('This installment template is not valid yet.'))
        if sys.valid_to and today > sys.valid_to:
            raise UserError(_('This installment template has expired.'))

        if sys.scope_project_enabled and sys.scope_project_id:
            if self.project_id != sys.scope_project_id:
                raise UserError(
                    _('This installment template is restricted to project "%s".')
                    % (sys.scope_project_id.display_name,)
                )
        if sys.scope_phase_enabled and sys.scope_phase_id:
            if self.sector_id != sys.scope_phase_id:
                raise UserError(
                    _('This installment template is restricted to phase "%s".')
                    % (sys.scope_phase_id.display_name,)
                )

        after_discount = base_price
        if sys.disc_type == 'percent':
            after_discount -= base_price * (sys.discount_percent or 0.0) / 100.0
        else:
            after_discount -= sys.discount_amount or 0.0

        if after_discount <= 0:
            raise UserError(_('Discount cannot exceed or equal the installment base amount.'))

        currency = self.currency_id or self.env.company.currency_id
        rounding = currency.rounding

        pen_rate = sys.penalty_percent if sys.pen_type == 'percent' else 0.0
        pen_fix = sys.penalty_amount if sys.pen_type == 'amount' else 0.0
        grace = sys.grace_period_days or 0

        start = self.installment_start_date or today

        # In form onchange, self.id may be unset/NewId; use the stored opportunity id.
        lead_db_id = self._origin.id or self.id
        if not lead_db_id:
            raise UserError(_('Save the opportunity before generating installments.'))

        lead_br = self.env['crm.lead'].browse(lead_db_id)
        lead_br.installment_line_ids.unlink()

        Line = self.env['real.estate.installment.line']

        dy = sys.duration_years or 0
        if dy <= 0:
            raise UserError(_('Set a positive installment duration (years) on the template.'))

        freq = sys.payment_frequency or 'monthly'
        periods_py = FREQUENCY_PERIODS_PER_YEAR[freq]
        step_reg = INSTALLMENT_STEP_MONTHS[freq]
        i_count = dy * periods_py
        if i_count <= 0:
            raise UserError(_('Invalid number of installments for this duration and frequency.'))

        if sys.dp_type == 'percent':
            dp_amt = after_discount * (sys.down_payment_percent or 0.0) / 100.0
        else:
            dp_amt = sys.down_payment_amount or 0.0

        bullet_total = 0.0
        bullet_scheduled = []
        for bl in sys.bullet_line_ids.sorted(lambda x: (x.sequence, x.id)):
            bfreq = bl.frequency or 'annual'
            n_bullets = int(dy * BULLET_PERIODS_PER_YEAR.get(bfreq, 1))
            step_bul = BULLET_STEP_MONTHS.get(bfreq, 12)
            if bl.value_type == 'percent':
                per_bullet = after_discount * (bl.amount_value or 0.0) / 100.0
            else:
                per_bullet = bl.amount_value or 0.0
            bullet_total += per_bullet * n_bullets
            if per_bullet <= 0 or n_bullets <= 0:
                continue
            seq_base = (bl.sequence or 10) * 10000
            for k in range(1, n_bullets + 1):
                bullet_scheduled.append({
                    'due_date': start + relativedelta(months=step_bul * k),
                    'amount': float_round(per_bullet, precision_rounding=rounding),
                    'installment_type': 'milestone',
                    '_seq': seq_base + k,
                })

        # Remaining principal split across regular installments (after DP and total bullets).
        amort_pool = after_discount - dp_amt - bullet_total
        if amort_pool < 0:
            raise UserError(
                _(
                    'Down payment plus total bullet amounts exceed the amount after discount. '
                    'Adjust the template.'
                )
            )

        entries = []
        if dp_amt > 0:
            entries.append({
                'due_date': start,
                'amount': float_round(dp_amt, precision_rounding=rounding),
                'installment_type': 'down_payment',
                '_seq': 0,
            })

        entries.extend(bullet_scheduled)

        piece = amort_pool / i_count
        partial_m = 0.0
        for i in range(i_count):
            due_m = start + relativedelta(months=step_reg * (i + 1))
            if i < i_count - 1:
                amt_m = float_round(piece, precision_rounding=rounding)
                partial_m += amt_m
            else:
                amt_m = float_round(amort_pool - partial_m, precision_rounding=rounding)
            entries.append({
                'due_date': due_m,
                'amount': amt_m,
                'installment_type': 'installment',
                '_seq': 500000 + i,
            })

        type_rank = {
            'down_payment': 0,
            'milestone': 2,
            'installment': 3,
        }
        entries.sort(
            key=lambda e: (
                e['due_date'],
                type_rank.get(e['installment_type'], 9),
                e.get('_seq', 0),
            )
        )

        seq = 1
        for e in entries:
            Line.create({
                'lead_id': lead_db_id,
                'installment_no': seq,
                'due_date': e['due_date'],
                'amount': e['amount'],
                'discount_amount': 0.0,
                'penalty_rate': pen_rate,
                'penalty_amount_fixed': pen_fix,
                'grace_days': grace,
                'installment_type': e['installment_type'],
            })
            seq += 1

    def action_generate_installment_schedule(self):
        """Rebuild schedule from template and show a notification."""
        self.ensure_one()
        self._generate_installment_schedule_from_template()
        nlines = len(self.installment_line_ids)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Installment schedule'),
                'message': _('Schedule generated: %(n)s lines.') % {'n': nlines},
                'type': 'success',
            },
        }

    @api.onchange('installment_system_id')
    def _onchange_installment_system_auto_schedule(self):
        """Regenerate lines when the template changes (saved opportunities only)."""
        if self.type != 'opportunity':
            return
        if not self._origin.id:
            return
        if not self.installment_system_id:
            self.installment_line_ids = [(5, 0, 0)]
            return
        if not self.unit_id:
            return
        try:
            self._generate_installment_schedule_from_template()
        except UserError as e:
            return {'warning': {'title': _('Installments'), 'message': e.args[0]}}

    def _auto_apply_installment_template_if_ready(self):
        """Called after save when template and unit allow generation."""
        for lead in self:
            if lead.type != 'opportunity':
                continue
            if not lead.installment_system_id:
                lead.installment_line_ids.unlink()
                continue
            if not lead.unit_id:
                continue
            lead._generate_installment_schedule_from_template()

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        leads._auto_apply_installment_template_if_ready()
        return leads

    def write(self, vals):
        res = super().write(vals)
        trigger = {
            'installment_system_id',
            'unit_id',
            'installment_base_price',
            'installment_start_date',
        }
        if trigger.intersection(vals.keys()):
            self._auto_apply_installment_template_if_ready()
        return res

    def action_share_unit_whatsapp(self):
        """Share unit details via WhatsApp"""
        self.ensure_one()
        if not self.unit_id:
            raise UserError(_('Please select a unit to share.'))
        
        return self.unit_id.action_share_whatsapp()
