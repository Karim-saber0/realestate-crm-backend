# -*- coding: utf-8 -*-
{
    'name': 'Real Estate CRM',
    'version': '18.0.6.0.0',
    'category': 'Sales/CRM',
    'summary': 'Comprehensive Real Estate CRM with Mobile App Backend',
    'description': """
        Real Estate CRM Module for Odoo 18 CE

        Features:
        - Project, Sector, Building, Unit management with geolocation
        - Enhanced CRM with real estate integration
        - LOI management and installment schedules linked to opportunities
        - WhatsApp integration for unit sharing
        - Mobile app backend APIs
        - Location-based activity tracking
        - Comprehensive reporting
    """,
    'author': 'Real Estate CRM Team',
    'website': 'https://www.odoo.com',
    'depends': [
        'base',
        'base_setup',
        'crm',
        'account',
        'mail',
        'contacts',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/data.xml',
        'data/installment_cron.xml',
        'views/project_views.xml',
        'views/sector_views.xml',
        'views/building_views.xml',
        'views/unit_category_views.xml',
        'views/unit_views.xml',
        'views/installment_system_views.xml',
        'views/installment_line_views.xml',
        'views/res_config_settings_views.xml',
        'views/crm_lead_views.xml',
        'views/crm_stage_views.xml',
        'views/activity_views.xml',
        'views/loi_views.xml',
        'views/menu_views.xml',
        'reports/report_loi.xml',
    ],
    'demo': [
        'demo/demo_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
