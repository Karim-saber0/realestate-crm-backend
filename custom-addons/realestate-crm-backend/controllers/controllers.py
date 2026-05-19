# -*- coding: utf-8 -*-

import odoo  
import odoo.modules.registry

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import UserError, AccessDenied, AccessError
import json
import logging
import werkzeug

_logger = logging.getLogger(__name__)


class RealEstateMobileAPI(http.Controller):

    def _require_explicit_session_for_api(self):
        """Require an authenticated Odoo session, or an explicit session token fallback."""
        path = request.httprequest.path.rstrip('/')
        if path.endswith('/real-estate/auth'):
            return None

        if request.session.uid:
            return None

        header = (request.httprequest.headers.get('X-Session-Id') or '').strip()
        query = (request.httprequest.args.get('session_id') or '').strip()
        if header or query:
            return None

        return self._json_response({
            'error': 'session_id required',
            'hint': 'Send the authenticated session cookie, or provide X-Session-Id / session_id fallback.',
        }, 401)

    def _cors_headers(self, response):
        """Add standard CORS headers for the local frontend."""
        response.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, PATCH, DELETE'
        response.headers['Access-Control-Allow-Headers'] = 'Origin, Content-Type, Accept, Authorization, X-Session-Id, X-Requested-With'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Vary'] = 'Origin'
        return response

    def _get_preflight_response(self):
        response = werkzeug.Response(status=200)
        response.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Session-Id'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    @http.route('/api/real-estate', type='http', auth='none', methods=['OPTIONS'], csrf=False)
    @http.route('/api/real-estate/<path:subpath>', type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def handle_cors_preflight(self, subpath=None, **kwargs):
        return self._get_preflight_response()

    def _log_request(self, operation, extra_info=None):
        """Log incoming API request with route, database, and session context."""
        route = request.httprequest.path
        method = request.httprequest.method
        remote_addr = request.httprequest.remote_addr
        db = request.db or request.session.db or 'unknown'
        session_id = request.httprequest.headers.get('X-Session-Id', 'none')
        
        log_msg = f'{operation} | route={route} | method={method} | db={db} | session_id={session_id[:16] if session_id != "none" else "none"}... | remote={remote_addr}'
        if extra_info:
            log_msg += f' | {extra_info}'
        _logger.info(log_msg)

    def _api_exec(self, operation, func):
        self._log_request(operation)
        guard = self._require_explicit_session_for_api()
        if guard is not None:
            return guard
        try:
            return func()
        except AccessDenied:
            _logger.warning(f'{operation}: Access denied for db={request.db}, user={request.env.user.id if hasattr(request.env, "user") else "unknown"}')
            return self._json_response({'error': 'Access denied'}, 403)
        except AccessError as e:
            _logger.warning(f'{operation}: AccessError - {str(e)}')
            return self._json_response({'error': str(e)}, 403)
        except UserError as e:
            msg = e.args[0] if e.args else str(e)
            _logger.warning(f'{operation}: UserError - {msg}')
            return self._json_response({'error': msg}, 400)
        except json.JSONDecodeError as e:
            _logger.warning(f'{operation}: Invalid JSON - {str(e)}')
            return self._json_response({'error': 'Invalid JSON body', 'detail': str(e)}, 400)
        except Exception as e:
            _logger.exception('%s API error (unhandled)', operation, exc_info=True)
            return self._json_response({'error': 'Request failed', 'operation': operation, 'detail': str(e)}, 500)

    def _api_exec_public(self, operation, func):
        self._log_request(operation)
        try:
            return func()
        except AccessDenied:
            _logger.warning(f'{operation}: Access denied during authentication')
            return self._json_response({'error': 'Invalid credentials'}, 401)
        except json.JSONDecodeError as e:
            _logger.warning(f'{operation}: Invalid JSON - {str(e)}')
            return self._json_response({'error': 'Invalid JSON body', 'detail': str(e)}, 400)
        except Exception as e:
            _logger.exception('%s API error (unhandled)', operation, exc_info=True)
            return self._json_response({'error': 'Authentication failed', 'detail': str(e)}, 500)

    @http.route('/api/real-estate/auth', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False)
    def authenticate(self, **kwargs):
        """Authenticate user for mobile app.

        JSON body: ``username``, ``password``, and ``database`` or ``db`` (Odoo DB name).
        If the session already has a DB (e.g. ``/web?db=...``), ``database`` may be omitted.
        On success, the JSON includes ``session_id`` (same value as the ``session_id`` cookie).
        """
        # Handle CORS preflight OPTIONS request
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()

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
            _logger.warning(f'authenticate: Database not provided (checked "database", "db", session.db)')
            return self._json_response({
                'error': 'Database required',
                'hint': 'Send the Odoo database name as "database" or "db" in the JSON body.',
            }, 400)

        if not http.db_filter([db]):
            _logger.warning(f'authenticate: Database "{db}" not found or not allowed by db_filter')
            return self._json_response({
                'error': 'Database not found or not allowed',
                'hint': f'Requested database "{db}" is not available. Check database name and server configuration.'
            }, 404)

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
            _logger.warning(f'authenticate: Authentication failed for user "{username}" on db "{db}" (no uid returned)')
            return self._json_response({'error': 'Invalid credentials'}, 401)

        if uid != request.session.uid:
            _logger.warning(f'authenticate: uid mismatch after auth - returned uid={uid}, session.uid={request.session.uid}, likely MFA required')
            return self._json_response({
                'error': 'Additional authentication required (e.g. multi-factor). Use web login.',
            }, 403)

        request.session.db = db
        registry = odoo.modules.registry.Registry(db)

        with registry.cursor() as cr:
            env = odoo.api.Environment(cr, request.session.uid, request.session.context)
            user = env['res.users'].browse(uid)

            _logger.info(f'authenticate: SUCCESS | user={user.login} (id={uid}) | db={db} | session={request.session.sid[:16]}...')
            
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
    @http.route('/api/real-estate/projects', type='http', auth='user', methods=['GET', 'OPTIONS'], csrf=False)
    def get_projects(self, **kwargs):
        """Get all active projects with the minimal portfolio payload."""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
        return self._api_exec('get_projects', self._get_projects_impl)

    def _get_projects_impl(self):
        projects = request.env['real.estate.project'].search([('active', '=', True)])
        result = []

        for project in projects:
            sector = project.sector_ids[:1] if project.sector_ids else None

            result.append({
                'id': project.id,
                'name': project.name,
                'code': project.code,
                'sector_id': [sector.id, sector.name] if sector else None,
                'location': project.location,
                'total_units': int(project.total_units or 0),
            })

        return self._json_response({'success': True, 'projects': result})

    @http.route('/api/real-estate/buildings', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def get_buildings(self, **kwargs):
        """Get active buildings, optionally filtered by project_id."""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
        return self._api_exec('get_buildings', self._get_buildings_impl)

    def _get_buildings_impl(self):
        params = request.params or {}
        domain = [('active', '=', True)]

        project_id = params.get('project_id')
        if project_id:
            try:
                domain.append(('project_id', '=', int(project_id)))
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid project_id'}, 400)

        buildings = request.env['real.estate.building'].search(domain)
        result = []

        for building in buildings:
            amenities = []
            if building.description:
                amenities.append(building.description)

            result.append({
                'id': building.id,
                'name': building.name,
                'project_id': [building.project_id.id, building.project_id.name] if building.project_id else None,
                'floors_count': int(building.floors or 0),
                'amenities': amenities,
            })

        return self._json_response({'success': True, 'buildings': result})

    @http.route('/api/real-estate/units', type='http', auth='user', methods=['GET', 'OPTIONS'], csrf=False)
    def get_units(self, **kwargs):
        """Get active units with spatial coordinates and optional filters."""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
        return self._api_exec('get_units', self._get_units_impl)

    def _get_units_impl(self):
        domain = [('active', '=', True)]
        params = request.params or {}

        project_id = params.get('project_id')
        if project_id:
            try:
                domain.append(('project_id', '=', int(project_id)))
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid project_id'}, 400)

        building_id = params.get('building_id')
        if building_id:
            try:
                domain.append(('building_id', '=', int(building_id)))
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid building_id'}, 400)

        status = params.get('status')
        if status:
            if status not in {'available', 'reserved', 'sold'}:
                return self._json_response({'error': 'Invalid status. Allowed values: available, reserved, sold'}, 400)
            domain.append(('status', '=', status))

        units = request.env['real.estate.unit'].search(domain)
        result = []

        for unit in units:
            result.append({
                'id': unit.id,
                'name': unit.name,
                'building_id': [unit.building_id.id, unit.building_id.name] if unit.building_id else None,
                'price': float(unit.price or 0.0),
                'status': unit.status,
                'floor': int(unit.floor or 0),
                'rooms_count': int((unit.bedrooms or 0) + (unit.bathrooms or 0)),
                'latitude': float(unit.latitude) if unit.latitude is not None else None,
                'longitude': float(unit.longitude) if unit.longitude is not None else None,
            })

        return self._json_response({'success': True, 'units': result})

    @http.route('/api/real-estate/opportunities', type='http', auth='user', methods=['GET', 'OPTIONS'], csrf=False)
    def get_opportunities(self, **kwargs):
        """Get opportunities for the current user"""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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

    @http.route('/api/real-estate/opportunities', type='http', auth='user', methods=['POST', 'OPTIONS'], csrf=False)
    def create_opportunity(self, **kwargs):
        """Create new opportunity with geolocation"""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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

    @http.route('/api/real-estate/opportunities/<int:opportunity_id>/stage', type='http', auth='user', methods=['POST', 'OPTIONS'], csrf=False)
    def update_opportunity_stage(self, opportunity_id, **kwargs):
        """Update opportunity stage and commercial values"""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
        return self._api_exec(
            'update_opportunity_stage',
            lambda: self._update_opportunity_stage_impl(opportunity_id),
        )

    def _update_opportunity_stage_impl(self, opportunity_id):
        opp, err = self._get_opportunity_for_user(opportunity_id)
        if err:
            return err

        data = json.loads(request.httprequest.data.decode('utf-8'))
        write_vals = {}

        if 'stage_id' in data:
            stage_id = data.get('stage_id')
            write_vals['stage_id'] = int(stage_id) if stage_id is not None else False

        if 'probability' in data:
            probability = data.get('probability')
            if probability is None:
                write_vals['probability'] = False
            else:
                try:
                    write_vals['probability'] = float(probability)
                except (TypeError, ValueError):
                    return self._json_response({'error': 'Invalid probability'}, 400)

        if 'expected_revenue' in data:
            expected_revenue = data.get('expected_revenue')
            if expected_revenue is None:
                write_vals['expected_revenue'] = False
            else:
                try:
                    write_vals['expected_revenue'] = float(expected_revenue)
                except (TypeError, ValueError):
                    return self._json_response({'error': 'Invalid expected_revenue'}, 400)

        if not write_vals:
            return self._json_response({'error': 'No valid fields provided'}, 400)

        opp.write(write_vals)
        return self._json_response({'success': True, 'message': 'Stage updated successfully'})

    @http.route('/api/real-estate/activities', type='http', auth='user', methods=['GET', 'OPTIONS'], csrf=False)
    def get_activities(self, **kwargs):
        """Get activities for the current user"""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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

    @http.route('/api/real-estate/activities', type='http', auth='user', methods=['POST', 'OPTIONS'], csrf=False)
    def create_activity(self, **kwargs):
        """Create new activity with geolocation"""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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

    @http.route('/api/real-estate/activities/<int:activity_id>/complete', type='http', auth='user', methods=['POST', 'OPTIONS'], csrf=False)
    def complete_activity(self, activity_id, **kwargs):
        """Complete activity with geolocation"""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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

    @http.route('/api/real-estate/contacts/<int:contact_id>/phone', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def get_contact_phone(self, contact_id, **kwargs):
        """Get contact phone number for click-to-call"""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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

    @http.route('/api/real-estate/contacts', type='http', auth='user', methods=['GET', 'OPTIONS'], csrf=False)
    def get_contacts(self, **kwargs):
        """Return active customer and lead-linked partner directory records."""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
        return self._api_exec('get_contacts', self._get_contacts_impl)

    def _get_contacts_impl(self):
        lead_partner_ids = request.env['crm.lead'].search([
            ('user_id', '=', request.env.user.id),
            ('partner_id', '!=', False),
        ]).mapped('partner_id.id')

        domain = [
            ('active', '=', True),
            '|',
            ('customer_rank', '>', 0),
            ('id', 'in', lead_partner_ids),
        ]

        contacts = request.env['res.partner'].search(domain, order='name')
        result = []

        for contact in contacts:
            result.append({
                'id': contact.id,
                'name': contact.name,
                'email': contact.email,
                'phone': contact.phone or contact.mobile,
                'company': contact.company_name or (contact.parent_id.name if contact.parent_id else None),
            })

        return self._json_response({'success': True, 'contacts': result})

    @http.route('/api/real-estate/contacts', type='http', auth='user', methods=['POST', 'OPTIONS'], csrf=False)
    def create_contact(self, **kwargs):
        """Create a contact record for the current user."""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
        return self._api_exec('create_contact', self._create_contact_impl)

    def _create_contact_impl(self):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        name = data.get('name')
        phone = data.get('phone')
        email = data.get('email')

        if not name:
            return self._json_response({'error': 'Contact name is required'}, 400)
        if not phone and not email:
            return self._json_response({'error': 'Phone or email is required'}, 400)

        contact_data = {
            'name': name,
            'email': email,
            'phone': phone,
            'mobile': data.get('mobile'),
            'city': data.get('city'),
            'comment': data.get('comment'),
            'user_id': request.env.user.id,
        }

        contact = request.env['res.partner'].create(contact_data)
        return self._json_response({
            'success': True,
            'contact_id': contact.id,
            'message': 'Contact created successfully',
        })

    @http.route('/api/real-estate/contacts/<int:contact_id>/update', type='http', auth='user', methods=['POST', 'OPTIONS'], csrf=False)
    def update_contact(self, contact_id, **kwargs):
        """Update a contact owned by or linked to the current user."""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
        return self._api_exec('update_contact', lambda: self._update_contact_impl(contact_id))

    def _get_contact_for_user(self, contact_id):
        contact = request.env['res.partner'].browse(contact_id)
        if not contact.exists():
            return None, self._json_response({'error': 'Contact not found'}, 404)

        if contact.user_id and contact.user_id.id == request.env.user.id:
            return contact, None

        partner_ids = request.env['crm.lead'].search([('user_id', '=', request.env.user.id), ('partner_id', '!=', False)]).mapped('partner_id.id')
        if contact.id in partner_ids:
            return contact, None

        return None, self._json_response({'error': 'Forbidden'}, 403)

    def _update_contact_impl(self, contact_id):
        contact, err = self._get_contact_for_user(contact_id)
        if err:
            return err

        data = json.loads(request.httprequest.data.decode('utf-8'))
        if not data:
            return self._json_response({'error': 'Request body is required'}, 400)

        name = data.get('name')
        phone = data.get('phone')
        email = data.get('email')

        if name is not None and not name:
            return self._json_response({'error': 'Contact name cannot be empty'}, 400)
        if (name or contact.name) and not (phone or email or contact.phone or contact.email):
            return self._json_response({'error': 'Phone or email is required'}, 400)

        write_vals = {}
        for field_name in ['name', 'email', 'phone', 'mobile', 'city', 'comment']:
            if field_name in data:
                write_vals[field_name] = data.get(field_name) or False

        if not write_vals:
            return self._json_response({'error': 'No fields provided for update'}, 400)

        contact.write(write_vals)
        return self._json_response({
            'success': True,
            'contact_id': contact.id,
            'message': 'Contact updated successfully',
        })

    @http.route('/api/real-estate/units/<int:unit_id>/whatsapp', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def get_unit_whatsapp_link(self, unit_id, **kwargs):
        """Get WhatsApp deep link for unit sharing"""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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

    @http.route('/api/real-estate/map-data', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def get_map_data(self, **kwargs):
        """Get all property locations for map display"""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
        return self._api_exec('get_map_data', self._get_map_data_impl)

    def _get_map_data_impl(self):
        # Get all projects with coordinates
        projects = request.env['real.estate.project'].search([
            ('active', '=', True),
            ('latitude', '!=', False),
            ('longitude', '!=', False)
        ])

        params = request.params or {}
        unit_domain = [
            ('active', '=', True),
            ('latitude', '!=', False),
            ('longitude', '!=', False),
        ]

        status = params.get('status')
        if status:
            unit_domain.append(('status', '=', status))

        unit_type = params.get('unit_type')
        if unit_type:
            unit_domain.append(('unit_type', '=', unit_type))

        project_id = params.get('project_id')
        if project_id:
            try:
                unit_domain.append(('project_id', '=', int(project_id)))
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid project_id'}, 400)

        min_price = params.get('min_price')
        if min_price:
            try:
                unit_domain.append(('price', '>=', float(min_price)))
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid min_price'}, 400)

        max_price = params.get('max_price')
        if max_price:
            try:
                unit_domain.append(('price', '<=', float(max_price)))
            except (TypeError, ValueError):
                return self._json_response({'error': 'Invalid max_price'}, 400)

        units = request.env['real.estate.unit'].search(unit_domain)

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

    @http.route('/api/real-estate/dashboard/analytics', type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def dashboard_analytics_preflight(self, **kwargs):
        """Separate OPTIONS handler for dashboard analytics preflight."""
        return self._get_preflight_response()

    @http.route('/api/real-estate/dashboard/analytics', type='http', auth='user', methods=['GET'], csrf=False)
    def get_dashboard_analytics(self, **kwargs):
        """Get high-level sales dashboard metrics."""
        return self._api_exec('get_dashboard_analytics', self._get_dashboard_analytics_impl)

    def _get_dashboard_analytics_impl(self):
        user_id = request.env.user.id
        opp_domain = [
            ('user_id', '=', user_id),
            ('type', '=', 'opportunity'),
            ('active', '=', True),
        ]

        total_opportunities = request.env['crm.lead'].search_count(opp_domain)
        revenue_data = request.env['crm.lead'].read_group(opp_domain, ['expected_revenue'], [])
        total_expected_revenue = (revenue_data and revenue_data[0].get('expected_revenue')) or 0.0

        won_deals_count = request.env['crm.lead'].search_count(opp_domain + [('stage_id.name', '=', 'Won')])
        pending_activities_count = request.env['mail.activity'].search_count([('user_id', '=', user_id)])
        available_units_count = request.env['real.estate.unit'].search_count([('status', '=', 'available')])

        return self._json_response({
            'success': True,
            'total_opportunities': total_opportunities,
            'total_expected_revenue': total_expected_revenue,
            'won_deals_count': won_deals_count,
            'pending_activities_count': pending_activities_count,
            'available_units_count': available_units_count,
        })

    def _json_response(self, data, status=200):
        """Helper method to return JSON response"""
        response = request.make_json_response(data)
        response.status_code = status
        return self._cors_headers(response)

    def _serialize_installment_template(self, tmpl):
        return {
            'id': int(tmpl.id),
            'name': tmpl.name,
            'down_payment_percentage': float(tmpl.down_payment_percent or 0.0),
            'number_of_installments': int(tmpl.installment_count or 0),
        }

    def _serialize_installment_line(self, line):
        if line.status == 'late':
            payment_status = 'overdue'
        elif line.status == 'paid':
            payment_status = 'paid'
        else:
            payment_status = 'pending'

        return {
            'id': int(line.id),
            'opportunity_id': int(line.lead_id.id if line.lead_id else 0),
            'amount': float(line.amount or 0.0),
            'due_date': line.due_date.isoformat() if line.due_date else None,
            'payment_status': payment_status,
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

    @http.route('/api/real-estate/installment-templates', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False)
    def get_installment_templates(self, **kwargs):
        """List active installment templates; optional project_id / sector_id match opportunity rules."""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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
        return self._json_response(result)

    @http.route(
        '/api/real-estate/opportunities/<int:opportunity_id>/installments',
        type='http',
        auth='none',
        methods=['GET', 'OPTIONS'],
        csrf=False,
    )
    def get_opportunity_installments(self, opportunity_id, **kwargs):
        """Installment schedule lines for an opportunity owned by the current user."""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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
        return self._json_response(lines)

    @http.route(
        '/api/real-estate/opportunities/<int:opportunity_id>/installments/regenerate',
        type='http',
        auth='none',
        methods=['POST', 'OPTIONS'],
        csrf=False,
    )
    def regenerate_opportunity_installments(self, opportunity_id, **kwargs):
        """Update optional installment fields and rebuild schedule (same logic as Generate Schedule)."""
        if request.httprequest.method == 'OPTIONS':
            return self._get_preflight_response()
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
