# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RealEstateUnitCategory(models.Model):
    _name = 'real.estate.unit.category'
    _description = 'Real Estate Unit Category'
    _order = 'parent_id, name'
    _rec_name = 'complete_name'

    name = fields.Char(
        string='Name',
        required=True
    )
    parent_id = fields.Many2one(
        'real.estate.unit.category',
        string='Parent Category',
        ondelete='cascade',
        index=True
    )
    child_ids = fields.One2many(
        'real.estate.unit.category',
        'parent_id',
        string='Child Categories'
    )
    complete_name = fields.Char(
        string='Complete Name',
        compute='_compute_complete_name',
        store=True
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for record in self:
            if record.parent_id:
                record.complete_name = '%s / %s' % (record.parent_id.complete_name, record.name)
            else:
                record.complete_name = record.name

    @api.constrains('parent_id')
    def _check_parent_loop(self):
        for record in self:
            parent = record.parent_id
            while parent:
                if parent == record:
                    raise ValidationError(_('You cannot create recursive categories.'))
                parent = parent.parent_id
