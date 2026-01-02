# Insumar_SP/__manifest__.py
{
    'name': 'Insumar SP',
    'version': '16.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Gestiona solicitudes de pedido entre sucursales y bodega central.',
    'author': 'Tu Nombre',
    'depends': ['stock', 'sales_team', 'mail', 'parches_insumar'],
    'data': [
        'data/insumar_sp_data.xml',
        'security/ir.model.access.csv',
        'security/insumar_sp_security.xml',
        'views/insumar_sp_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}