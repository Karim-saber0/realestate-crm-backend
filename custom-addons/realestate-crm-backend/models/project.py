# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RealEstateProject(models.Model):
    _name = 'real.estate.project'
    _description = 'Real Estate Project'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(
        string='Project Name',
        required=True,
        help='Name of the real estate project'
    )
    code = fields.Char(
        string='Project Code',
        required=True,
        help='Unique code for the project'
    )
    description = fields.Text(
        string='Description',
        help='Detailed description of the project'
    )
    developer_id = fields.Many2one(
        'res.partner',
        string='Developer',
        required=True,
        help='Company or developer responsible for the project'
    )
    location = fields.Char(
        string='Location',
        required=True,
        help='General location/address of the project'
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
    city = fields.Char(
        string='City',
        required=True
    )
    state_id = fields.Many2one(
        'res.country.state',
        string='State',
        domain="[('country_id', '=', country_id)]"
    )
    country_id = fields.Many2one(
        'res.country',
        string='Country',
        required=True,
        default=lambda self: self.env.company.country_id
    )
    zip = fields.Char(
        string='ZIP Code'
    )
    project_type = fields.Selection([
        ('residential', 'Residential'),
        ('commercial', 'Commercial'),
        ('mixed', 'Mixed Use'),
        ('industrial', 'Industrial'),
    ], string='Project Type', required=True, default='residential')
    
    status = fields.Selection([
        ('planning', 'Planning'),
        ('construction', 'Under Construction'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='planning')
    
    start_date = fields.Date(
        string='Start Date',
        help='Project start date'
    )
    completion_date = fields.Date(
        string='Expected Completion Date',
        help='Expected project completion date'
    )
    
    total_units = fields.Integer(
        string='Total Units',
        compute='_compute_total_units',
        store=True,
        help='Total number of units in the project'
    )
    
    sector_ids = fields.One2many(
        'real.estate.sector',
        'project_id',
        string='Sectors'
    )
    
    unit_ids = fields.One2many(
        'real.estate.unit',
        'project_id',
        string='Units'
    )
    
    opportunity_ids = fields.One2many(
        'crm.lead',
        'project_id',
        string='Opportunities'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )

    @api.depends('unit_ids', 'sector_ids.unit_ids', 'sector_ids.building_ids.unit_ids')
    def _compute_total_units(self):
        for project in self:
            # Count units linked directly to the project, via sectors, and via buildings
            units_direct = project.unit_ids
            units_from_sectors = project.sector_ids.mapped('unit_ids')
            units_from_buildings = project.sector_ids.mapped('building_ids').mapped('unit_ids')
            all_units = (units_direct | units_from_sectors | units_from_buildings)
            project.total_units = len(all_units)

    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        for record in self:
            if record.latitude and (record.latitude < -90 or record.latitude > 90):
                raise ValidationError(_('Latitude must be between -90 and 90 degrees.'))
            if record.longitude and (record.longitude < -180 or record.longitude > 180):
                raise ValidationError(_('Longitude must be between -180 and 180 degrees.'))

    @api.constrains('code')
    def _check_code_unique(self):
        for record in self:
            if self.search_count([('code', '=', record.code), ('id', '!=', record.id)]) > 0:
                raise ValidationError(_('Project code must be unique.'))

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} ({record.code})"
            result.append((record.id, name))
        return result

    def action_view_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Units'),
            'res_model': 'real.estate.unit',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_view_opportunities(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Opportunities'),
            'res_model': 'crm.lead',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
