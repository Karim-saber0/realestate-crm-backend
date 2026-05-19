# -*- coding: utf-8 -*-

import re

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RealEstateSector(models.Model):
    _name = 'real.estate.sector'
    _description = 'Real Estate Sector'
    _order = 'project_id, name'
    _rec_name = 'name'

    name = fields.Char(
        string='Sector Name',
        required=True,
        help='Name of the sector within the project'
    )
    code = fields.Char(
        string='Sector Code',
        required=True,
        help='Unique code for the sector within the project'
    )
    description = fields.Text(
        string='Description',
        help='Detailed description of the sector'
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
    location = fields.Char(
        string='Location',
        help='Specific location within the project'
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
    
    sector_type = fields.Selection([
        ('residential', 'Residential'),
        ('commercial', 'Commercial'),
        ('mixed', 'Mixed Use'),
        ('amenities', 'Amenities'),
        ('parking', 'Parking'),
    ], string='Sector Type', required=True, default='residential')
    
    status = fields.Selection([
        ('planning', 'Planning'),
        ('construction', 'Under Construction'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
    ], string='Status', default='planning')
    
    number_of_buildings = fields.Integer(
        string='Number of Buildings',
        default=0,
        help='Desired number of buildings to maintain in this sector'
    )
    
    building_code_start = fields.Char(
        string='Building Start Code',
        help='Code seed used when auto-generating buildings (e.g., B01)'
    )
    
    building_count = fields.Integer(
        string='Existing Buildings',
        compute='_compute_building_count',
        store=False,
        help='Current number of buildings linked to this sector'
    )
    
    total_units = fields.Integer(
        string='Total Units',
        compute='_compute_total_units',
        store=True,
        help='Total number of units in the sector'
    )
    
    building_ids = fields.One2many(
        'real.estate.building',
        'sector_id',
        string='Buildings'
    )
    
    unit_ids = fields.One2many(
        'real.estate.unit',
        'sector_id',
        string='Units'
    )
    
    opportunity_ids = fields.One2many(
        'crm.lead',
        'sector_id',
        string='Opportunities'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )

    @api.depends('unit_ids')
    def _compute_total_units(self):
        for sector in self:
            sector.total_units = len(sector.unit_ids)
    
    @api.depends('building_ids')
    def _compute_building_count(self):
        for sector in self:
            sector.building_count = len(sector.building_ids)

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
                raise ValidationError(_('Sector code must be unique within the project.'))

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.project_id.name} - {record.name} ({record.code})"
            result.append((record.id, name))
        return result

    def action_view_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Units'),
            'res_model': 'real.estate.unit',
            'view_mode': 'list,form',
            'domain': [('sector_id', '=', self.id)],
            'context': {'default_sector_id': self.id},
        }

    def action_view_opportunities(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Opportunities'),
            'res_model': 'crm.lead',
            'view_mode': 'list,form',
            'domain': [('sector_id', '=', self.id)],
            'context': {'default_sector_id': self.id},
        }

    def action_generate_buildings(self):
        for sector in self:
            sector._generate_buildings()

    def _generate_buildings(self):
        self.ensure_one()

        if not self.project_id:
            raise ValidationError(_('Please assign a project before generating buildings.'))

        if self.number_of_buildings <= 0:
            raise ValidationError(_('Number of buildings must be greater than zero.'))

        if not self.building_code_start:
            raise ValidationError(_('Please set a building start code before generation.'))

        target_total = self.number_of_buildings
        existing_buildings = self.building_ids
        to_create = target_total - len(existing_buildings)

        if to_create <= 0:
            raise ValidationError(_('This sector already has %s buildings.') % len(existing_buildings))

        try:
            prefix, number, width = self._split_code(self.building_code_start)
        except ValueError as exc:
            raise ValidationError(str(exc))

        next_number = number or 1
        existing_codes = set(existing_buildings.mapped('code'))

        Building = self.env['real.estate.building']
        created_count = 0

        for i in range(to_create):
            code_candidate, next_number = self._next_available_code(prefix, next_number, width, existing_codes)

            building_vals = {
                'name': f"{self.name} - Building {len(existing_buildings) + created_count + 1}",
                'code': code_candidate,
                'project_id': self.project_id.id,
                'sector_id': self.id,
                'location': self.location,
                'latitude': self.latitude,
                'longitude': self.longitude,
            }
            Building.create(building_vals)
            created_count += 1
            existing_codes.add(code_candidate)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Buildings Generated'),
                'message': _('%s new building(s) created.') % to_create,
                'type': 'success',
            }
        }

    @staticmethod
    def _split_code(code):
        """Split code into prefix, numeric part, and width."""
        if not code:
            raise ValueError(_('Building start code cannot be empty.'))
        match = re.match(r'^(.*?)(\d+)$', str(code))
        if not match:
            raise ValueError(_('Building start code must end with digits, e.g., "B01".'))
        prefix, number_str = match.groups()
        number_int = int(number_str)
        width = len(number_str)
        return prefix, number_int, width

    @staticmethod
    def _next_available_code(prefix, start_number, width, existing_codes):
        """Return a unique code and next number."""
        number = start_number
        suffix_width = width if width > 0 else 1

        while True:
            number_str = str(number)
            if suffix_width > 0:
                number_str = number_str.zfill(suffix_width)
            candidate = f"{prefix}{number_str}"

            if candidate not in existing_codes:
                next_number = number + 1
                return candidate, next_number

            number += 1
