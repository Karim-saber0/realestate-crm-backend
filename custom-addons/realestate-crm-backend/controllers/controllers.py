# -*- coding: utf-8 -*-

import odoo
import odoo.modules.registry

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import UserError, AccessDenied, AccessError
import json
import logging

_logger = logging.getLogger(__name__)


class RealEstateMobileAPI(http.Controller):

    def _require_explicit_session_for_api(self):
        """Require ``X-Session-Id`` header or ``session_id`` query param (cookie alone is not enough)."""
        path = request.httprequest.path.rstrip('/')
        if path.endswith('/real-estate/auth'):
            return None
        header = (request.httprequest.headers.get('X-Session-Id') or '').strip()
        query = (request.httprequest.args.get('session_id') or '').strip()
        if header or query:
            return None
        return self._json_response({
            'error': 'session_id required',
            'hint': 'Send header X-Session-Id or query parameter session_id (see POST /api/real-estate/auth).',
        }, 401)

    def _api_exec(self, operation, func):
        guard = self._require_explicit_session_for_api()
        if guard is not None:
            return guard
        try:
            return func()
        except AccessDenied:
            return self._json_response({'error': 'Access denied'}, 403)
        except AccessError as e:
            return self._json_response({'error': str(e)}, 403)
        except UserError as e:
            msg = e.args[0] if e.args else str(e)
            return self._json_response({'error': msg}, 400)
        except json.JSONDecodeError:
            return self._json_response({'error': 'Invalid JSON body'}, 400)
        except Exception as e:
            _logger.exception('%s API error', operation, exc_info=True)
            return self._json_response({'error': 'Request failed', 'operation': operation}, 500)

    def _api_exec_public(self, operation, func):
        try:
            return func()
        except AccessDenied:
            return self._json_response({'error': 'Invalid credentials'}, 401)
        except json.JSONDecodeError:
            return self._json_response({'error': 'Invalid JSON body'}, 400)
        except Exception as e:
            _logger.exception('%s API error', operation, exc_info=True)
            return self._json_response({'error': 'Authentication failed'}, 500)

    @http.route('/api/real-estate/auth', type='http', auth='none', methods=['POST'], csrf=False)
    def authenticate(self, **kwargs):
        """Authenticate user for mobile app.

        JSON body: ``username``, ``password``, and ``database`` or ``db`` (Odoo DB name).
        If the session already has a DB (e.g. ``/web?db=...``), ``database`` may be omitted.
        On success, the JSON includes ``session_id`` (same value as the ``session_id`` cookie).
        """
        return self._api_exec_public('authenticate', self._authenticate_impl)

    def _authenticate_impl(self):
        data = json.loads(request.httprequest.data.decode('utf-8'))

        # Support username OR login OR email
        username = (
                data.get('username')
                or data.get('login')
                or data.get('email')
        )

        # Support password OR pass
        password = (
                data.get('password')
                or data.get('pass')
        )

        # Support database OR db
        db = (
                data.get('database')
                or data.get('db')
                or request.session.db
        )

        if not username or not password:
            return self._json_response({
                'error': 'Username and password required',
                'hint': 'Send username/login and password in JSON body.'
            }, 400)

        if not db:
            return self._json_response({
                'error': 'Database required',
                'hint': 'Send the Odoo database name as "database" or "db" in the JSON body.',
            }, 400)

        if not http.db_filter([db]):
            return self._json_response({'error': 'Database not found or not allowed'}, 404)

        if request.db and request.db != db:
            request.env.cr.close()
        elif request.db:
            request.env.cr.rollback()

        credential = {
            'type': 'password',
            'login': username,
            'password': password
        }

        try:
            auth_info = request.session.authenticate(db, credential)
        except TypeError:
            auth_info = request.session.authenticate(db, username, password)

        if isinstance(auth_info, dict):
            uid = auth_info.get('uid')
        elif isinstance(auth_info, bool):
            uid = request.session.uid if auth_info else None
        else:
            uid = auth_info

        if not uid:
            return self._json_response({'error': 'Invalid credentials'}, 401)

        if uid != request.session.uid:
            return self._json_response({
                'error': 'Additional authentication required (e.g. multi-factor). Use web login.',
            }, 403)

        request.session.db = db
        registry = odoo.modules.registry.Registry(db)

        with registry.cursor() as cr:
            env = odoo.api.Environment(cr, request.session.uid, request.session.context)
            user = env['res.users'].browse(uid)

            return self._json_response({
                'success': True,
                'session_id': request.session.sid,
                'database': db,
                'user_id': user.id,
                'username': user.login,
                'name': user.name,
                'email': user.email,
                'company_id': user.company_id.id,
                'company_name': user.company_id.name,
            })
    @http.route('/api/real-estate/projects', type='http', auth='user', methods=['GET'])
    def get_projects(self, **kwargs):
        """Get all projects with geolocation data"""
        return self._api_exec('get_projects', self._get_projects_impl)

    def _get_projects_impl(self):
        projects = request.env['real.estate.project'].search([('active', '=', True)])
        result = []

        for project in projects:
            result.append({
                'id': project.id,
                'name': project.name,
                'code': project.code,
                'description': project.description,
                'developer': project.developer_id.name,
                'location': project.location,
                'latitude': project.latitude,
                'longitude': project.longitude,
                'city': project.city,
                'state': project.state_id.name if project.state_id else None,
                'country': project.country_id.name if project.country_id else None,
                'project_type': project.project_type,
                'status': project.status,
                'total_units': project.total_units,
                'start_date': project.start_date.isoformat() if project.start_date else None,
                'completion_date': project.completion_date.isoformat() if project.completion_date else None,
            })

        return self._json_response({'success': True, 'projects': result})

    @http.route('/api/real-estate/units', type='http', auth='user', methods=['GET'])
    def get_units(self, **kwargs):
        """Get all units with geolocation data"""
        return self._api_exec('get_units', self._get_units_impl)

    def _get_units_impl(self):
        domain = [('active', '=', True)]
        params = request.params or {}

        # Filter by project if provided (query string)
        project_id = params.get('project_id')
        if project_id:
            try:
                domain.append(('project_id', '=', int(project_id)))
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid project_id'}, 400)

        # Filter by status if provided
        status = params.get('status')
        if status:
            domain.append(('status', '=', status))

        units = request.env['real.estate.unit'].search(domain)
        result = []

        for unit in units:
            result.append({
                'id': unit.id,
                'name': unit.name,
                'code': unit.code,
                'description': unit.description,
                'project_id': unit.project_id.id,
                'project_name': unit.project_id.name,
                'sector_id': unit.sector_id.id,
                'sector_name': unit.sector_id.name,
                'building_id': unit.building_id.id,
                'building_name': unit.building_id.name,
                'floor': unit.floor,
                'unit_type': unit.unit_type,
                'bedrooms': unit.bedrooms,
                'bathrooms': unit.bathrooms,
                'area_sqft': unit.area_sqft,
                'area_sqm': unit.area_sqm,
                'price': unit.price,
                'currency': unit.currency_id.name if unit.currency_id else None,
                'location': unit.location,
                'latitude': unit.latitude,
                'longitude': unit.longitude,
                'status': unit.status,
                'features': unit.features,
                'balcony': unit.balcony,
                'parking': unit.parking,
                'furnished': unit.furnished,
            })

        return self._json_response({'success': True, 'units': result})

    @http.route('/api/real-estate/opportunities', type='http', auth='user', methods=['GET'])
    def get_opportunities(self, **kwargs):
        """Get opportunities for the current user"""
        return self._api_exec('get_opportunities', self._get_opportunities_impl)

    def _get_opportunities_impl(self):
        opportunities = request.env['crm.lead'].search([
            ('user_id', '=', request.env.user.id),
            ('type', '=', 'opportunity')
        ])
        result = []

        for opp in opportunities:
            result.append({
                'id': opp.id,
                'name': opp.name,
                'partner_id': opp.partner_id.id if opp.partner_id else None,
                'partner_name': opp.partner_id.name if opp.partner_id else None,
                'project_id': opp.project_id.id if opp.project_id else None,
                'project_name': opp.project_id.name if opp.project_id else None,
                'unit_id': opp.unit_id.id if opp.unit_id else None,
                'unit_name': opp.unit_id.name if opp.unit_id else None,
                'property_type': opp.property_type,
                'expected_revenue': opp.expected_revenue,
                'probability': opp.probability,
                'stage_id': opp.stage_id.id if opp.stage_id else None,
                'stage_name': opp.stage_id.name if opp.stage_id else None,
                'agent_latitude': opp.agent_latitude,
                'agent_longitude': opp.agent_longitude,
                'create_date': opp.create_date.isoformat(),
                'write_date': opp.write_date.isoformat(),
            })

        return self._json_response({'success': True, 'opportunities': result})

    @http.route('/api/real-estate/opportunities', type='http', auth='user', methods=['POST'], csrf=False)
    def create_opportunity(self, **kwargs):
        """Create new opportunity with geolocation"""
        return self._api_exec('create_opportunity', self._create_opportunity_impl)

    def _create_opportunity_impl(self):
        data = json.loads(request.httprequest.data.decode('utf-8'))

        # Extract geolocation from data
        agent_latitude = data.get('agent_latitude')
        agent_longitude = data.get('agent_longitude')

        # Create opportunity
        opportunity_data = {
            'name': data.get('name'),
            'type': data.get('type', 'opportunity'),
            'partner_id': data.get('partner_id'),
            'project_id': data.get('project_id'),
            'sector_id': data.get('sector_id'),
            'building_id': data.get('building_id'),
            'unit_id': data.get('unit_id'),
            'property_type': data.get('property_type', 'residential'),
            'expected_revenue': data.get('expected_revenue'),
            'probability': data.get('probability', 10),
            'user_id': request.env.user.id,
            'agent_latitude': agent_latitude,
            'agent_longitude': agent_longitude,
        }

        opportunity = request.env['crm.lead'].create(opportunity_data)

        return self._json_response({
            'success': True,
            'opportunity_id': opportunity.id,
            'message': 'Opportunity created successfully'
        })

    @http.route('/api/real-estate/activities', type='http', auth='user', methods=['GET'])
    def get_activities(self, **kwargs):
        """Get activities for the current user"""
        return self._api_exec('get_activities', self._get_activities_impl)

    def _get_activities_impl(self):
        activities = request.env['mail.activity'].search([
            ('user_id', '=', request.env.user.id)
        ])
        result = []

        for activity in activities:
            result.append({
                'id': activity.id,
                'summary': activity.summary,
                'activity_type_id': activity.activity_type_id.id if activity.activity_type_id else None,
                'activity_type_name': activity.activity_type_id.name if activity.activity_type_id else None,
                'res_model': activity.res_model,
                'res_id': activity.res_id,
                'date_deadline': activity.date_deadline.isoformat() if activity.date_deadline else None,
                'agent_latitude': activity.agent_latitude,
                'agent_longitude': activity.agent_longitude,
                'completion_latitude': activity.completion_latitude,
                'completion_longitude': activity.completion_longitude,
                'property_related': activity.property_related,
                'project_id': activity.project_id.id if activity.project_id else None,
                'unit_id': activity.unit_id.id if activity.unit_id else None,
                'state': activity.state,
                'create_date': activity.create_date.isoformat(),
            })

        return self._json_response({'success': True, 'activities': result})

    @http.route('/api/real-estate/activities', type='http', auth='user', methods=['POST'], csrf=False)
    def create_activity(self, **kwargs):
        """Create new activity with geolocation"""
        return self._api_exec('create_activity', self._create_activity_impl)

    def _create_activity_impl(self):
        data = json.loads(request.httprequest.data.decode('utf-8'))

        # Extract geolocation from data
        agent_latitude = data.get('agent_latitude')
        agent_longitude = data.get('agent_longitude')

        # Create activity
        activity_data = {
            'summary': data.get('summary'),
            'res_model': data.get('res_model'),
            'res_id': data.get('res_id'),
            'user_id': request.env.user.id,
            'date_deadline': data.get('date_deadline'),
            'agent_latitude': agent_latitude,
            'agent_longitude': agent_longitude,
        }

        # Accept activity_type via id or name (backward compatibility: 'activity_type' as name)
        activity_type_id = data.get('activity_type_id')
        activity_type_name = data.get('activity_type_name') or data.get('activity_type')
        if activity_type_id:
            activity_data['activity_type_id'] = activity_type_id
        elif activity_type_name:
            atype = request.env['mail.activity.type'].sudo().search([('name', '=', activity_type_name)], limit=1)
            if atype:
                activity_data['activity_type_id'] = atype.id

        activity = request.env['mail.activity'].create(activity_data)

        return self._json_response({
            'success': True,
            'activity_id': activity.id,
            'message': 'Activity created successfully'
        })

    @http.route('/api/real-estate/activities/<int:activity_id>/complete', type='http', auth='user', methods=['POST'], csrf=False)
    def complete_activity(self, activity_id, **kwargs):
        """Complete activity with geolocation"""
        return self._api_exec('complete_activity', lambda: self._complete_activity_impl(activity_id))

    def _complete_activity_impl(self, activity_id):
        data = json.loads(request.httprequest.data.decode('utf-8'))

        # Extract completion geolocation from data
        completion_latitude = data.get('completion_latitude')
        completion_longitude = data.get('completion_longitude')

        activity = request.env['mail.activity'].browse(activity_id)
        if not activity.exists():
            return self._json_response({'error': 'Activity not found'}, 404)

        # Update completion geolocation
        if completion_latitude and completion_longitude:
            activity.write({
                'completion_latitude': completion_latitude,
                'completion_longitude': completion_longitude,
            })

        # Complete the activity
        activity.action_done()

        return self._json_response({
            'success': True,
            'message': 'Activity completed successfully'
        })

    @http.route('/api/real-estate/contacts/<int:contact_id>/phone', type='http', auth='user', methods=['GET'])
    def get_contact_phone(self, contact_id, **kwargs):
        """Get contact phone number for click-to-call"""
        return self._api_exec('get_contact_phone', lambda: self._get_contact_phone_impl(contact_id))

    def _get_contact_phone_impl(self, contact_id):
        contact = request.env['res.partner'].browse(contact_id)
        if not contact.exists():
            return self._json_response({'error': 'Contact not found'}, 404)

        return self._json_response({
            'success': True,
            'contact_id': contact.id,
            'name': contact.name,
            'phone': contact.phone,
            'mobile': contact.mobile,
            'email': contact.email,
        })

    @http.route('/api/real-estate/units/<int:unit_id>/whatsapp', type='http', auth='user', methods=['GET'])
    def get_unit_whatsapp_link(self, unit_id, **kwargs):
        """Get WhatsApp deep link for unit sharing"""
        return self._api_exec('get_unit_whatsapp_link', lambda: self._get_unit_whatsapp_link_impl(unit_id))

    def _get_unit_whatsapp_link_impl(self, unit_id):
        import urllib.parse

        unit = request.env['real.estate.unit'].browse(unit_id)
        if not unit.exists():
            return self._json_response({'error': 'Unit not found'}, 404)

        # Create the message content
        message = f"""🏠 *{unit.name}* - {unit.project_id.name}

            📍 *Location:* {unit.location or 'N/A'}
            🏢 *Building:* {unit.building_id.name}
            🏗️ *Sector:* {unit.sector_id.name}
            🏠 *Type:* {dict(unit._fields['unit_type'].selection)[unit.unit_type]}
            📐 *Area:* {unit.area_sqft} sq ft ({unit.area_sqm:.2f} sq m)
            💰 *Price:* {unit.price:,.2f} {unit.currency_id.symbol if unit.currency_id else ''}
            🛏️ *Bedrooms:* {unit.bedrooms}
            🚿 *Bathrooms:* {unit.bathrooms}

            {unit.description or ''}

            #RealEstate #Property #ForSale"""

        # Create map link if coordinates are available
        map_link = ""
        if unit.latitude and unit.longitude:
            map_link = f"\n🗺️ *Location:* https://maps.google.com/?q={unit.latitude},{unit.longitude}"
            message += map_link

        # Create WhatsApp deep link
        whatsapp_url = f"https://wa.me/?text={urllib.parse.quote(message)}"

        return self._json_response({
            'success': True,
            'unit_id': unit.id,
            'whatsapp_url': whatsapp_url,
            'message': message,
        })

    @http.route('/api/real-estate/map-data', type='http', auth='user', methods=['GET'])
    def get_map_data(self, **kwargs):
        """Get all property locations for map display"""
        return self._api_exec('get_map_data', self._get_map_data_impl)

    def _get_map_data_impl(self):
        # Get all projects with coordinates
        projects = request.env['real.estate.project'].search([
            ('active', '=', True),
            ('latitude', '!=', False),
            ('longitude', '!=', False)
        ])

        # Get all units with coordinates
        units = request.env['real.estate.unit'].search([
            ('active', '=', True),
            ('latitude', '!=', False),
            ('longitude', '!=', False)
        ])

        result = {
            'projects': [],
            'units': []
        }

        for project in projects:
            result['projects'].append({
                'id': project.id,
                'name': project.name,
                'latitude': project.latitude,
                'longitude': project.longitude,
                'type': 'project',
                'status': project.status,
            })

        for unit in units:
            result['units'].append({
                'id': unit.id,
                'name': unit.name,
                'project_name': unit.project_id.name,
                'latitude': unit.latitude,
                'longitude': unit.longitude,
                'type': 'unit',
                'status': unit.status,
                'price': unit.price,
                'unit_type': unit.unit_type,
            })

        return self._json_response({'success': True, 'data': result})

    def _json_response(self, data, status=200):
        """Helper method to return JSON response"""
        response = request.make_json_response(data)
        response.status_code = status
        return response

    def _serialize_installment_template(self, tmpl):
        return {
            'id': tmpl.id,
            'code': tmpl.code,
            'name': tmpl.name,
            'active': tmpl.active,
            'valid_from': tmpl.valid_from.isoformat() if tmpl.valid_from else None,
            'valid_to': tmpl.valid_to.isoformat() if tmpl.valid_to else None,
            'duration_years': tmpl.duration_years,
            'payment_frequency': tmpl.payment_frequency,
            'installments_per_year': tmpl.installments_per_year,
            'installment_count': tmpl.installment_count,
            'dp_type': tmpl.dp_type,
            'down_payment_percent': tmpl.down_payment_percent,
            'down_payment_amount': tmpl.down_payment_amount,
            'disc_type': tmpl.disc_type,
            'discount_percent': tmpl.discount_percent,
            'discount_amount': tmpl.discount_amount,
            'pen_type': tmpl.pen_type,
            'penalty_percent': tmpl.penalty_percent,
            'penalty_amount': tmpl.penalty_amount,
            'grace_period_days': tmpl.grace_period_days,
            'scope_project_enabled': tmpl.scope_project_enabled,
            'scope_project_id': tmpl.scope_project_id.id if tmpl.scope_project_id else None,
            'scope_project_name': tmpl.scope_project_id.name if tmpl.scope_project_id else None,
            'scope_phase_enabled': tmpl.scope_phase_enabled,
            'scope_phase_id': tmpl.scope_phase_id.id if tmpl.scope_phase_id else None,
            'scope_phase_name': tmpl.scope_phase_id.name if tmpl.scope_phase_id else None,
            'bullet_lines': [
                {
                    'id': bl.id,
                    'sequence': bl.sequence,
                    'name': bl.name,
                    'frequency': bl.frequency,
                    'value_type': bl.value_type,
                    'amount_value': bl.amount_value,
                }
                for bl in tmpl.bullet_line_ids.sorted(lambda x: (x.sequence, x.id))
            ],
        }

    def _serialize_installment_line(self, line):
        return {
            'id': line.id,
            'installment_no': line.installment_no,
            'installment_type': line.installment_type,
            'due_date': line.due_date.isoformat() if line.due_date else None,
            'amount': line.amount,
            'discount_amount': line.discount_amount,
            'penalty_rate': line.penalty_rate,
            'penalty_amount_fixed': line.penalty_amount_fixed,
            'grace_days': line.grace_days,
            'remaining_installment': line.remaining_installment,
            'remaining_penalty': line.remaining_penalty,
            'total_payable': line.total_payable,
            'status': line.status,
            'currency': line.currency_id.name if line.currency_id else None,
        }

    def _get_opportunity_for_user(self, opportunity_id):
        """Return crm.lead browse or (None, error_response)."""
        opp = request.env['crm.lead'].browse(int(opportunity_id))
        if not opp.exists():
            return None, self._json_response({'error': 'Opportunity not found'}, 404)
        if opp.type != 'opportunity':
            return None, self._json_response({'error': 'Not an opportunity'}, 400)
        if not opp.user_id or opp.user_id.id != request.env.user.id:
            return None, self._json_response({'error': 'Forbidden'}, 403)
        return opp, None

    @http.route('/api/real-estate/installment-templates', type='http', auth='user', methods=['GET'])
    def get_installment_templates(self, **kwargs):
        """List active installment templates; optional project_id / sector_id match opportunity rules."""
        return self._api_exec('get_installment_templates', self._get_installment_templates_impl)

    def _get_installment_templates_impl(self):
        params = request.params or {}
        project_id = params.get('project_id')
        sector_id = params.get('sector_id')
        active_leaf = ('active', '=', True)

        if project_id and sector_id:
            try:
                pid = int(project_id)
                sid = int(sector_id)
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid project_id or sector_id'}, 400)
            domain = [
                '&',
                '&',
                active_leaf,
                '|',
                '|',
                ('scope_project_enabled', '=', False),
                ('scope_project_id', '=', False),
                ('scope_project_id', '=', pid),
                '|',
                '|',
                ('scope_phase_enabled', '=', False),
                ('scope_phase_id', '=', False),
                ('scope_phase_id', '=', sid),
            ]
        elif project_id:
            try:
                pid = int(project_id)
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid project_id'}, 400)
            domain = [
                '&',
                active_leaf,
                '|',
                '|',
                ('scope_project_enabled', '=', False),
                ('scope_project_id', '=', False),
                ('scope_project_id', '=', pid),
            ]
        elif sector_id:
            try:
                sid = int(sector_id)
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid sector_id'}, 400)
            domain = [
                '&',
                active_leaf,
                '|',
                '|',
                ('scope_phase_enabled', '=', False),
                ('scope_phase_id', '=', False),
                ('scope_phase_id', '=', sid),
            ]
        else:
            domain = [active_leaf]
        templates = request.env['real.estate.installment.system'].search(domain, order='code')
        result = [self._serialize_installment_template(t) for t in templates]
        return self._json_response({'success': True, 'templates': result})

    @http.route(
        '/api/real-estate/opportunities/<int:opportunity_id>/installments',
        type='http',
        auth='user',
        methods=['GET'],
    )
    def get_opportunity_installments(self, opportunity_id, **kwargs):
        """Installment schedule lines for an opportunity owned by the current user."""
        return self._api_exec(
            'get_opportunity_installments',
            lambda: self._get_opportunity_installments_impl(opportunity_id),
        )

    def _get_opportunity_installments_impl(self, opportunity_id):
        opp, err = self._get_opportunity_for_user(opportunity_id)
        if err:
            return err
        lines = [
            self._serialize_installment_line(line)
            for line in opp.installment_line_ids.sorted('installment_no')
        ]
        return self._json_response({
            'success': True,
            'opportunity_id': opp.id,
            'installment_system_id': opp.installment_system_id.id if opp.installment_system_id else None,
            'installment_system_name': opp.installment_system_id.name if opp.installment_system_id else None,
            'installment_base_price': opp.installment_base_price,
            'installment_start_date': opp.installment_start_date.isoformat()
            if opp.installment_start_date
            else None,
            'unit_price': opp.unit_price,
            'lines': lines,
        })

    @http.route(
        '/api/real-estate/opportunities/<int:opportunity_id>/installments/regenerate',
        type='http',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def regenerate_opportunity_installments(self, opportunity_id, **kwargs):
        """Update optional installment fields and rebuild schedule (same logic as Generate Schedule)."""
        return self._api_exec(
            'regenerate_opportunity_installments',
            lambda: self._regenerate_opportunity_installments_impl(opportunity_id),
        )

    def _regenerate_opportunity_installments_impl(self, opportunity_id):
        opp, err = self._get_opportunity_for_user(opportunity_id)
        if err:
            return err
        data = {}
        if request.httprequest.data:
            try:
                data = json.loads(request.httprequest.data.decode('utf-8'))
            except json.JSONDecodeError:
                return self._json_response({'error': 'Invalid JSON body'}, 400)

        write_vals = {}
        if 'installment_system_id' in data:
            write_vals['installment_system_id'] = data.get('installment_system_id') or False
        if 'installment_base_price' in data:
            write_vals['installment_base_price'] = data.get('installment_base_price')
        if 'installment_start_date' in data:
            write_vals['installment_start_date'] = data.get('installment_start_date') or False
        if write_vals:
            opp.write(write_vals)

        opp._generate_installment_schedule_from_template()
        lines = [
            self._serialize_installment_line(line)
            for line in opp.installment_line_ids.sorted('installment_no')
        ]
        return self._json_response({
            'success': True,
            'message': 'Schedule regenerated.',
            'opportunity_id': opp.id,
            'lines_count': len(lines),
            'lines': lines,
        })