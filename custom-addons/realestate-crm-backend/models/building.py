# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RealEstateBuilding(models.Model):
    _name = 'real.estate.building'
    _description = 'Real Estate Building'
    _order = 'project_id, sector_id, name'
    _rec_name = 'name'

    name = fields.Char(
        string='Building Name',
        required=True,
        help='Name of the building'
    )
    code = fields.Char(
        string='Building Code',
        required=True,
        help='Unique code for the building'
    )
    description = fields.Text(
        string='Description',
        help='Detailed description of the building'
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
    sector_id = fields.Many2one(
        'real.estate.sector',
        string='Sector',
        required=True,
        ondelete='cascade'
    )
    location = fields.Char(
        string='Location',
        help='Specific location of the building'
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
    
    building_type = fields.Selection([
        ('apartment', 'Apartment Building'),
        ('villa', 'Villa'),
        ('townhouse', 'Townhouse'),
        ('office', 'Office Building'),
        ('retail', 'Retail Building'),
        ('warehouse', 'Warehouse'),
        ('mixed', 'Mixed Use'),
    ], string='Building Type', required=True, default='apartment')
    
    status = fields.Selection([
        ('planning', 'Planning'),
        ('construction', 'Under Construction'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
    ], string='Status', default='planning')
    
    floors = fields.Integer(
        string='Number of Floors',
        default=1,
        help='Total number of floors in the building'
    )
    
    total_units = fields.Integer(
        string='Total Units',
        compute='_compute_total_units',
        store=True,
        help='Total number of units in the building'
    )
    
    unit_ids = fields.One2many(
        'real.estate.unit',
        'building_id',
        string='Units'
    )
    
    opportunity_ids = fields.One2many(
        'crm.lead',
        'building_id',
        string='Opportunities'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )

    @api.depends('unit_ids')
    def _compute_total_units(self):
        for building in self:
            building.total_units = len(building.unit_ids)

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
                raise ValidationError(_('Building code must be unique within the project.'))

    @api.constrains('sector_id')
    def _check_sector_project(self):
        for record in self:
            if record.sector_id and record.project_id and record.sector_id.project_id != record.project_id:
                raise ValidationError(_('Sector must belong to the same project.'))

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.project_id.name} - {record.sector_id.name} - {record.name} ({record.code})"
            result.append((record.id, name))
        return result

    def action_view_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Units'),
            'res_model': 'real.estate.unit',
            'view_mode': 'list,form',
            'domain': [('building_id', '=', self.id)],
            'context': {'default_building_id': self.id},
        }

    def action_view_opportunities(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Opportunities'),
            'res_model': 'crm.lead',
            'view_mode': 'list,form',
            'domain': [('building_id', '=', self.id)],
            'context': {'default_building_id': self.id},
        }
