{
    'name': 'Solicitud de Pedido (SP Request)',
    'version': '16.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Gestiona solicitudes de pedido entre sucursales y bodega central.',
    'author': 'Tu Nombre',
    'depends': ['stock', 'sales_team', 'mail'],
    'data': [
        'data/sp_request_data.xml',
        'security/ir.model.access.csv',
        'security/sp_request_security.xml',
        'views/sp_request_views.xml',  # <-- Único archivo de vistas
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}