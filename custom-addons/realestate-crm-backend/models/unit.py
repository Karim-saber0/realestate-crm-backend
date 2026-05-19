# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import json


class RealEstateUnit(models.Model):
    _name = 'real.estate.unit'
    _description = 'Real Estate Unit'
    _order = 'project_id, sector_id, building_id, floor, name'
    _rec_name = 'name'

    name = fields.Char(
        string='Unit Name',
        required=True,
        help='Name or number of the unit'
    )
    code = fields.Char(
        string='Unit Code',
        required=True,
        help='Unique code for the unit'
    )
    description = fields.Text(
        string='Description',
        help='Detailed description of the unit'
    )
    project_id = fields.Many2one(
        'real.estate.project',
        string='Project',
        required=True,
        ondelete='cascade'
    )
    developer_id = fields.Many2one(
        'res.partner',
        string='Developer',
        related='project_id.developer_id',
        store=True,
        readonly=True,
        help='Developer inherited from the project'
    )
    broker_id = fields.Many2one(
        'res.partner',
        string='Broker',
        help='Broker/agent responsible for selling this unit'
    )
    unit_category_id = fields.Many2one(
        'real.estate.unit.category',
        string='Unit Type',
        domain=[('parent_id', '=', False)],
        help='Main unit type/category'
    )
    unit_subcategory_id = fields.Many2one(
        'real.estate.unit.category',
        string='Unit Sub Type',
        domain="[('parent_id', '=', unit_category_id)]",
        help='Sub type under the selected unit type'
    )
    sector_id = fields.Many2one(
        'real.estate.sector',
        string='Sector',
        required=True,
        ondelete='cascade'
    )
    building_id = fields.Many2one(
        'real.estate.building',
        string='Building',
        required=True,
        ondelete='cascade'
    )
    
    # Unit Details
    floor = fields.Integer(
        string='Floor',
        required=True,
        default=1,
        help='Floor number where the unit is located'
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
    ], string='Unit Type', required=True, default='br1')
    
    bedrooms = fields.Integer(
        string='Bedrooms',
        default=1
    )
    bathrooms = fields.Integer(
        string='Bathrooms',
        default=1
    )
    area_sqft = fields.Float(
        string='Area (Sq Ft)',
        digits=(10, 2),
        help='Unit area in square feet'
    )
    area_sqm = fields.Float(
        string='Area (Sq M)',
        digits=(10, 2),
        compute='_compute_area_sqm',
        store=True,
        help='Unit area in square meters'
    )
    
    # Pricing
    price = fields.Monetary(
        string='Price',
        currency_field='currency_id',
        help='Unit selling price'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    
    # Location
    location = fields.Char(
        string='Location',
        help='Specific location description'
    )
    latitude = fields.Float(
        string='Latitude',
        digits=(10, 7),
        help='Geographic latitude coordinate'
    )
    longitude = fields.Float(
        string='Longitude',
        digits=(10, 7),
        help='Geographic longitude coordinate'
    )
    
    # Status
    status = fields.Selection([
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('sold', 'Sold'),
        ('rented', 'Rented'),
        ('maintenance', 'Under Maintenance'),
        ('not_ready', 'Not Ready'),
    ], string='Status', default='available')
    
    # Features
    features = fields.Text(
        string='Features',
        help='Special features and amenities of the unit'
    )
    balcony = fields.Boolean(
        string='Has Balcony',
        default=False
    )
    parking = fields.Boolean(
        string='Has Parking',
        default=False
    )
    furnished = fields.Boolean(
        string='Furnished',
        default=False
    )
    
    # Related Records
    opportunity_ids = fields.One2many(
        'crm.lead',
        'unit_id',
        string='Opportunities'
    )
    
    loi_ids = fields.One2many(
        'real.estate.loi',
        'unit_id',
        string='Letters of Intent'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )

    @api.depends('area_sqft')
    def _compute_area_sqm(self):
        for unit in self:
            unit.area_sqm = unit.area_sqft * 0.092903 if unit.area_sqft else 0

    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        for record in self:
            if record.latitude and (record.latitude < -90 or record.latitude > 90):
                raise ValidationError(_('Latitude must be between -90 and 90 degrees.'))
            if record.longitude and (record.longitude < -180 or record.longitude > 180):
                raise ValidationError(_('Longitude must be between -180 and 180 degrees.'))

    @api.constrains('code', 'project_id')
    def _check_code_unique(self):
        for record in self:
            if self.search_count([
                ('code', '=', record.code), 
                ('project_id', '=', record.project_id.id),
                ('id', '!=', record.id)
            ]) > 0:
                raise ValidationError(_('Unit code must be unique within the project.'))

    @api.constrains('sector_id', 'building_id')
    def _check_hierarchy(self):
        for record in self:
            if record.sector_id and record.project_id and record.sector_id.project_id != record.project_id:
                raise ValidationError(_('Sector must belong to the same project.'))
            if record.building_id and record.sector_id and record.building_id.sector_id != record.sector_id:
                raise ValidationError(_('Building must belong to the same sector.'))

    @api.constrains('unit_category_id', 'unit_subcategory_id')
    def _check_unit_subcategory(self):
        for record in self:
            if record.unit_subcategory_id and record.unit_subcategory_id.parent_id != record.unit_category_id:
                raise ValidationError(_('Unit sub type must belong to the selected unit type.'))

    @api.onchange('unit_category_id')
    def _onchange_unit_category_id(self):
        if self.unit_subcategory_id and self.unit_subcategory_id.parent_id != self.unit_category_id:
            self.unit_subcategory_id = False

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.project_id.name} - {record.sector_id.name} - {record.building_id.name} - {record.name} ({record.code})"
            result.append((record.id, name))
        return result

    def action_share_whatsapp(self):
        """Generate WhatsApp deep link for unit sharing"""
        self.ensure_one()
        
        # Create the message content
        message = f"""🏠 *{self.name}* - {self.project_id.name}

📍 *Location:* {self.location or 'N/A'}
🏢 *Building:* {self.building_id.name}
🏗️ *Sector:* {self.sector_id.name}
🏠 *Type:* {dict(self._fields['unit_type'].selection)[self.unit_type]}
📐 *Area:* {self.area_sqft} sq ft ({self.area_sqm:.2f} sq m)
💰 *Price:* {self.price:,.2f} {self.currency_id.symbol if self.currency_id else ''}
🛏️ *Bedrooms:* {self.bedrooms}
🚿 *Bathrooms:* {self.bathrooms}

{self.description or ''}

#RealEstate #Property #ForSale"""

        # Create map link if coordinates are available
        map_link = ""
        if self.latitude and self.longitude:
            map_link = f"\n🗺️ *Location:* https://maps.google.com/?q={self.latitude},{self.longitude}"
            message += map_link

        # Create WhatsApp deep link
        whatsapp_url = f"https://wa.me/?text={requests.utils.quote(message)}"
        
        return {
            'type': 'ir.actions.act_url',
            'url': whatsapp_url,
            'target': 'new',
        }

    def action_view_opportunities(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Opportunities'),
            'res_model': 'crm.lead',
            'view_mode': 'list,form',
            'domain': [('unit_id', '=', self.id)],
            'context': {'default_unit_id': self.id},
        }

    def action_view_lois(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Letters of Intent'),
            'res_model': 'real.estate.loi',
            'view_mode': 'list,form',
            'domain': [('unit_id', '=', self.id)],
            'context': {'default_unit_id': self.id},
        }

