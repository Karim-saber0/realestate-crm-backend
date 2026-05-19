# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta


class RealEstateLOI(models.Model):
    _name = 'real.estate.loi'
    _description = 'Letter of Intent'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='LOI Number',
        required=True,
        default=lambda self: _('New'),
        help='Letter of Intent reference number'
    )
    
    # Related Records
    opportunity_id = fields.Many2one(
        'crm.lead',
        string='Opportunity',
        required=True,
        ondelete='cascade'
    )
    unit_id = fields.Many2one(
        'real.estate.unit',
        string='Unit',
        required=True,
        ondelete='cascade'
    )
    customer_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        ondelete='cascade'
    )
    
    # Unit Details (Auto-populated)
    project_id = fields.Many2one(
        'real.estate.project',
        string='Project',
        related='unit_id.project_id',
        store=True
    )
    sector_id = fields.Many2one(
        'real.estate.sector',
        string='Sector',
        related='unit_id.sector_id',
        store=True
    )
    building_id = fields.Many2one(
        'real.estate.building',
        string='Building',
        related='unit_id.building_id',
        store=True
    )
    
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
    
    # Pricing
    unit_price = fields.Monetary(
        string='Unit Price',
        related='unit_id.price',
        store=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='unit_id.currency_id',
        store=True
    )
    
    # LOI Terms
    loi_date = fields.Date(
        string='LOI Date',
        required=True,
        default=fields.Date.context_today
    )
    
    validity_days = fields.Integer(
        string='Validity (Days)',
        default=30,
        help='Number of days the LOI is valid'
    )
    
    expiry_date = fields.Date(
        string='Expiry Date',
        compute='_compute_expiry_date',
        store=True,
        help='Date when the LOI expires'
    )
    
    status = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('converted', 'Converted to Contract'),
    ], string='Status', default='draft')
    
    # Terms and Conditions
    reservation_amount = fields.Monetary(
        string='Reservation Amount',
        currency_field='currency_id',
        help='Amount to be paid as reservation'
    )
    
    payment_terms = fields.Text(
        string='Payment Terms',
        help='Payment terms and conditions'
    )
    
    special_conditions = fields.Text(
        string='Special Conditions',
        help='Any special conditions or requirements'
    )
    
    # Geolocation
    unit_latitude = fields.Float(
        string='Unit Latitude',
        related='unit_id.latitude',
        store=True,
        help='Unit latitude coordinate'
    )
    unit_longitude = fields.Float(
        string='Unit Longitude',
        related='unit_id.longitude',
        store=True,
        help='Unit longitude coordinate'
    )
    
    # Documents
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'loi_attachment_rel',
        'loi_id',
        'attachment_id',
        string='Attachments'
    )
    
    # Notes
    notes = fields.Text(
        string='Notes',
        help='Additional notes and comments'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )

    @api.depends('loi_date', 'validity_days')
    def _compute_expiry_date(self):
        for loi in self:
            if loi.loi_date and loi.validity_days:
                loi.expiry_date = loi.loi_date + timedelta(days=loi.validity_days)
            else:
                loi.expiry_date = False

    @api.model
    def create(self, vals):
        """Override create to generate LOI number"""
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('real.estate.loi') or _('New')
        return super().create(vals)

    @api.constrains('validity_days')
    def _check_validity_days(self):
        for record in self:
            if record.validity_days <= 0:
                raise ValidationError(_('Validity days must be greater than 0.'))

    @api.constrains('reservation_amount')
    def _check_reservation_amount(self):
        for record in self:
            if record.reservation_amount and record.reservation_amount < 0:
                raise ValidationError(_('Reservation amount cannot be negative.'))

    def action_send_loi(self):
        """Send LOI to customer"""
        self.ensure_one()
        self.status = 'sent'
        
        # Create mail template and send
        template = self.env.ref('real_estate_crm.email_template_loi', raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('LOI Sent'),
                'message': _('Letter of Intent has been sent to the customer.'),
                'type': 'success',
            }
        }

    def action_accept(self):
        """Accept the LOI"""
        self.ensure_one()
        self.status = 'accepted'
        
        # Update opportunity status
        if self.opportunity_id:
            self.opportunity_id.loi_id = self.id
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('LOI Accepted'),
                'message': _('Letter of Intent has been accepted.'),
                'type': 'success',
            }
        }

    def action_reject(self):
        """Reject the LOI"""
        self.ensure_one()
        self.status = 'rejected'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('LOI Rejected'),
                'message': _('Letter of Intent has been rejected.'),
                'type': 'warning',
            }
        }

    def action_convert_to_contract(self):
        """Convert LOI to contract"""
        self.ensure_one()
        self.status = 'converted'
        
        # Here you would typically create a contract or invoice
        # For now, we'll just update the status
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('LOI Converted'),
                'message': _('Letter of Intent has been converted to contract.'),
                'type': 'success',
            }
        }

    def action_view_unit_location(self):
        """View unit location on map"""
        self.ensure_one()
        if self.unit_latitude and self.unit_longitude:
            map_url = f"https://maps.google.com/?q={self.unit_latitude},{self.unit_longitude}"
            return {
                'type': 'ir.actions.act_url',
                'url': map_url,
                'target': 'new',
            }
        else:
            raise UserError(_('No location data available for this unit.'))

    def action_print_loi(self):
        """Print LOI document"""
        self.ensure_one()
        return self.env.ref('real_estate_crm.action_report_loi').report_action(self)

    @api.model
    def _cron_check_expired_lois(self):
        """Cron job to check and mark expired LOIs"""
        today = fields.Date.today()
        expired_lois = self.search([
            ('status', 'in', ['sent', 'accepted']),
            ('expiry_date', '<', today)
        ])
        
        for loi in expired_lois:
            loi.status = 'expired'
        
        if expired_lois:
            _logger.info(f'Marked {len(expired_lois)} LOIs as expired.')
