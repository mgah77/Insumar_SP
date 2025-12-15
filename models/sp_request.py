from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError

class SpRequest(models.Model):
    _name = 'sp.request'
    _description = 'Solicitud de Pedido'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, index=True, default=lambda self: _('Nuevo'))
    date = fields.Datetime(string='Fecha', required=True, readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Creado por', required=True, readonly=True, default=lambda self: self.env.user)
    warehouse_id = fields.Many2one('stock.warehouse', string='Bodega', required=True, tracking=True)
    line_ids = fields.One2many('sp.request.line', 'request_id', string='Líneas de Producto')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('review', 'Revisión'),
        ('validated', 'Validación'),
        ('done', 'Entregado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    # Campo auxiliar para la vista, calculado dinámicamente
    is_branch_user = fields.Boolean(compute='_compute_user_type', store=False)

    @api.depends_context('uid')
    def _compute_user_type(self):
        # Es usuario de sucursal si tiene una bodega asignada en su perfil
        for record in self:
            record.is_branch_user = bool(self.env.user.property_warehouse_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Si el usuario tiene bodega asignada, la usa y no puede cambiarla
            if self.env.user.property_warehouse_id:
                vals['warehouse_id'] = self.env.user.property_warehouse_id.id
            
            # Generar nombre
            if 'name' not in vals or vals['name'] == _('Nuevo'):
                warehouse = self.env['stock.warehouse'].browse(vals.get('warehouse_id'))
                seq = self.env['ir.sequence'].next_by_code('sp.request') or _('Nuevo')
                warehouse_code = warehouse.code if warehouse else 'XX'
                vals['name'] = f"SP/{warehouse_code}/{seq}"
        
        return super().create(vals_list)

    def write(self, vals):
        # Restricción para Usuario de Sucursal (con bodega asignada)
        if self.env.user.property_warehouse_id:
            for record in self:
                if record.state != 'draft':
                    raise UserError(_("Solo puedes editar una Solicitud de Pedido en estado Borrador."))
        return super().write(vals)

    def unlink(self):
        # Restricción para Usuario de Sucursal (con bodega asignada)
        if self.env.user.property_warehouse_id:
            for record in self:
                if record.state != 'draft':
                    raise UserError(_("Solo puedes eliminar una Solicitud de Pedido en estado Borrador."))
        return super().unlink()

    # --- Sobrescritura del método search para filtrar visibilidad ---
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        # Si el usuario tiene bodega asignada, filtrar para que solo vea sus SPs
        if self.env.user.property_warehouse_id:
            args = args + [('warehouse_id', '=', self.env.user.property_warehouse_id.id)]
        # Si no tiene bodega asignada (usuario central), no se aplica ningún filtro.
        return super().search(args, offset, limit, order, count=count)

    # --- Métodos para los botones de flujo ---
    def action_send_review(self):
        # Acción permitida solo para usuarios con bodega asignada
        if not self.env.user.property_warehouse_id:
            raise AccessError(_("Esta acción solo está disponible para usuarios de sucursal."))
        self.write({'state': 'review'})

    def action_validate(self):
        # Acción permitida solo para usuarios SIN bodega asignada (usuarios centrales)
        if self.env.user.property_warehouse_id:
            raise AccessError(_("Esta acción solo está disponible para usuarios centrales."))
        self.write({'state': 'validated'})

    def action_mark_done(self):
        # Acción permitida solo para usuarios SIN bodega asignada (usuarios centrales)
        if self.env.user.property_warehouse_id:
            raise AccessError(_("Esta acción solo está disponible para usuarios centrales."))
        self.write({'state': 'done'})

    def action_recalculate_stock(self):
        self.ensure_one()
        if self.state != 'validated':
            raise UserError(_("Esta acción solo se puede realizar en estado 'Validación'."))
        
        self.line_ids._compute_stock_info()
        self.message_post(body=_("Stock recalculado manualmente."))


class SpRequestLine(models.Model):
    _name = 'sp.request.line'
    _description = 'Línea de Solicitud de Pedido'
    _order = 'stock_central desc, id' # Orden inteligente: con stock central primero

    request_id = fields.Many2one('sp.request', string='Solicitud de Pedido', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    qty_request = fields.Float(string='Cant. Solicitada', digits='Product Unit of Measure', required=True, default=1.0)
    
    # Campos de control y stock
    stock_branch = fields.Float(string='Stock en Sucursal', digits='Product Unit of Measure', store=True, compute='_compute_stock_info')
    stock_central = fields.Float(string='Stock Central', digits='Product Unit of Measure', store=True, compute='_compute_stock_info')
    avg_sales_3m = fields.Float(string='Ventas Prom. 3m', digits='Product Unit of Measure', compute='_compute_avg_sales')
    move_qty = fields.Float(string='Cant. a Mover', digits='Product Unit of Measure')

    # --- Campos computados ---
    @api.depends('product_id', 'request_id.warehouse_id')
    def _compute_stock_info(self):
        # Buscar la bodega central por su código 'WH'
        central_warehouse = self.env['stock.warehouse'].search([('code', '=', 'WH')], limit=1)
        
        for line in self:
            if not line.product_id:
                line.stock_branch = 0
                line.stock_central = 0
                continue

            # Stock en la bodega de la solicitud
            line.stock_branch = line.product_id.with_context(warehouse=line.request_id.warehouse_id.id).virtual_available

            # Stock en bodega central
            if central_warehouse:
                line.stock_central = line.product_id.with_context(warehouse=central_warehouse.id).virtual_available
            else:
                # Si no se encuentra una bodega con código 'WH', el stock es 0
                line.stock_central = 0

    @api.depends('product_id')
    def _compute_avg_sales(self):
        for line in self:
            if not line.product_id:
                line.avg_sales_3m = 0
                continue
            
            # Calcular promedio de ventas de los últimos 90 días
            from_date = fields.Datetime.now() - fields.RelativeDelta(days=90)
            sales_data = self.env['sale.report'].read_group(
                domain=[('product_id', '=', line.product_id.id), ('date', '>=', from_date)],
                fields=['product_uom_qty'],
                groupby=[]
            )
            total_sales = sales_data[0]['product_uom_qty'] if sales_data else 0.0
            line.avg_sales_3m = total_sales / 3.0 if total_sales > 0 else 0.0