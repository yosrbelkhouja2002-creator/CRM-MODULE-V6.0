{
    'name': 'CRM Menu Override',
    'version': '1.0',
    'category': 'CRM',
    'summary': 'Override Leads menu',
    'license': 'LGPL-3',
    'depends': ['crm'],
    'data': [
        'security/ir.model.access.csv',
         'views/piste_source_view.xml',
    'views/opportunity_workflow_view.xml',  
    'views/crm_menu_override.xml',
    ],
    'installable': True,
    'auto_install': False,
}
