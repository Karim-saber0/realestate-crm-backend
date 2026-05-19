# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    # Geolocation Fields
    agent_latitude = fields.Float(
        string='Agent Latitude',
        digits=(10, 7),
        help='Agent location latitude when activity was created'
    )
    agent_longitude = fields.Float(
        string='Agent Longitude',
        digits=(10, 7),
        help='Agent location longitude when activity was created'
    )
    
    completion_latitude = fields.Float(
        string='Completion Latitude',
        digits=(10, 7),
        help='Agent location latitude when activity was completed'
    )
    completion_longitude = fields.Float(
        string='Completion Longitude',
        digits=(10, 7),
        help='Agent location longitude when activity was completed'
    )
    
    # Real Estate Specific Fields
    property_related = fields.Boolean(
        string='Property Related',
        default=False,
        help='Indicates if this activity is related to a property'
    )
    
    project_id = fields.Many2one(
        'real.estate.project',
        string='Project',
        help='Related project if activity is property-related'
    )
    
    unit_id = fields.Many2one(
        'real.estate.unit',
        string='Unit',
        help='Related unit if activity is property-related'
    )
    
    # Activity Type Enhancement
    # NOTE: In Odoo 18, mail.activity uses activity_type_id (Many2one).
    # To add new types, use data records (see data/data.xml).

    @api.constrains('agent_latitude', 'agent_longitude', 'completion_latitude', 'completion_longitude')
    def _check_coordinates(self):
        for record in self:
            coordinates = [
                ('agent_latitude', record.agent_latitude),
                ('agent_longitude', record.agent_longitude),
                ('completion_latitude', record.completion_latitude),
                ('completion_longitude', record.completion_longitude),
            ]
            
            for field_name, value in coordinates:
                if value and (value < -90 if 'latitude' in field_name else value < -180):
                    min_val = -90 if 'latitude' in field_name else -180
                    max_val = 90 if 'latitude' in field_name else 180
                    raise ValidationError(_('%s must be between %s and %s degrees.') % (
                        self._fields[field_name].string, min_val, max_val))
                if value and (value > 90 if 'latitude' in field_name else value > 180):
                    min_val = -90 if 'latitude' in field_name else -180
                    max_val = 90 if 'latitude' in field_name else 180
                    raise ValidationError(_('%s must be between %s and %s degrees.') % (
                        self._fields[field_name].string, min_val, max_val))

    @api.model
    def create(self, vals):
        """Override create to capture geolocation if provided"""
        # If geolocation is provided in context (from mobile app)
        if self.env.context.get('agent_latitude') and self.env.context.get('agent_longitude'):
            vals.update({
                'agent_latitude': self.env.context.get('agent_latitude'),
                'agent_longitude': self.env.context.get('agent_longitude'),
            })
        
        # Auto-detect if activity is property-related
        if vals.get('res_model') == 'real.estate.unit':
            vals['property_related'] = True
            vals['unit_id'] = vals.get('res_id')
        elif vals.get('res_model') == 'real.estate.project':
            vals['property_related'] = True
            vals['project_id'] = vals.get('res_id')
        
        return super().create(vals)

    def action_done(self):
        """Override action_done to capture completion geolocation"""
        # If completion geolocation is provided in context (from mobile app)
        if self.env.context.get('completion_latitude') and self.env.context.get('completion_longitude'):
            self.write({
                'completion_latitude': self.env.context.get('completion_latitude'),
                'completion_longitude': self.env.context.get('completion_longitude'),
            })
        
        return super().action_done()

    def action_view_location(self):
        """Open location in maps"""
        self.ensure_one()
        if self.agent_latitude and self.agent_longitude:
            map_url = f"https://maps.google.com/?q={self.agent_latitude},{self.agent_longitude}"
            return {
                'type': 'ir.actions.act_url',
                'url': map_url,
                'target': 'new',
            }
        else:
            raise UserError(_('No location data available for this activity.'))

    def action_view_completion_location(self):
        """Open completion location in maps"""
        self.ensure_one()
        if self.completion_latitude and self.completion_longitude:
            map_url = f"https://maps.google.com/?q={self.completion_latitude},{self.completion_longitude}"
            return {
                'type': 'ir.actions.act_url',
                'url': map_url,
                'target': 'new',
            }
        else:
            raise UserError(_('No completion location data available for this activity.'))
