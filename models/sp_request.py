from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError
from dateutil.relativedelta import relativedelta

class SpRequest(models.Model):
    _name = 'insumar_sp.request'
    _description = 'Solicitud de Pedido'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, index=True, default=lambda self: _('Nuevo'))
    date = fields.Datetime(string='Fecha', required=True, readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Creado por', required=True, readonly=True, default=lambda self: self.env.user)
    warehouse_id = fields.Many2one('stock.warehouse', string='Bodega', required=True, tracking=True)
    line_ids = fields.One2many('insumar_sp.line', 'request_id', string='Líneas de Producto')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('review', 'Revisión'),
        ('validated', 'Validación'),
        ('done', 'Entregado'),
    ], string='Estado', default='draft', required=True, tracking=True)

    is_branch_user = fields.Boolean(compute='_compute_user_type', store=False)

    @api.depends_context('uid')
    def _compute_user_type(self):
        for record in self:
            record.is_branch_user = bool(self.env.user.property_warehouse_id)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.user.property_warehouse_id:
            res['warehouse_id'] = self.env.user.property_warehouse_id.id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.env.user.property_warehouse_id:
                vals['warehouse_id'] = self.env.user.property_warehouse_id.id
            else:
                if not vals.get('warehouse_id'):
                    raise UserError(_("Debe seleccionar una bodega para crear una Solicitud de Pedido."))
            
            if 'name' not in vals or vals['name'] == _('Nuevo'):
                warehouse = self.env['stock.warehouse'].browse(vals.get('warehouse_id'))
                seq = self.env['ir.sequence'].next_by_code('insumar_sp.request') or _('Nuevo')
                warehouse_code = warehouse.code if warehouse else 'XX'
                vals['name'] = f"SP/{warehouse_code}/{seq}"
        
        return super().create(vals_list)

    def write(self, vals):
        if self.env.user.property_warehouse_id:
            for record in self:
                if record.state != 'draft':
                    raise UserError(_("Solo puedes editar una Solicitud de Pedido en estado Borrador."))
        return super().write(vals)

    def unlink(self):
        if self.env.user.property_warehouse_id:
            for record in self:
                if record.state != 'draft':
                    raise UserError(_("Solo puedes eliminar una Solicitud de Pedido en estado Borrador."))
        return super().unlink()

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if self.env.user.property_warehouse_id:
            args = args + [('warehouse_id', '=', self.env.user.property_warehouse_id.id)]
        return super().search(args, offset, limit, order, count=count)

    def action_send_review(self):
        if not self.env.user.property_warehouse_id:
            raise AccessError(_("Esta acción solo está disponible para usuarios de sucursal."))
        self.write({'state': 'review'})

    def action_validate(self):
        if self.env.user.property_warehouse_id:
            raise AccessError(_("Esta acción solo está disponible para usuarios centrales."))
        self.write({'state': 'validated'})

    def action_mark_done(self):
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
    _name = 'insumar_sp.line'
    _description = 'Línea de Solicitud de Pedido'
    _order = 'stock_central desc, id'

    request_id = fields.Many2one('insumar_sp.request', string='Solicitud de Pedido', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    qty_request = fields.Float(string='Cant. Solicitada', digits='Product Unit of Measure', required=True, default=1.0)
    
    stock_branch = fields.Float(string='Stock en Sucursal', digits='Product Unit of Measure', store=True, compute='_compute_stock_info')
    stock_central = fields.Float(string='Stock Central', digits='Product Unit of Measure', store=True, compute='_compute_stock_info')
    avg_sales_3m = fields.Float(string='Ventas Prom. 3m', digits='Product Unit of Measure', compute='_compute_avg_sales')
    move_qty = fields.Float(string='Cant. a Mover', digits='Product Unit of Measure')

    show_red_alert = fields.Boolean(compute='_compute_show_red_alert', store=False)
    can_see_stock_central = fields.Boolean(compute='_compute_can_see_stock_central', store=False)

    @api.depends_context('uid')
    def _compute_can_see_stock_central(self):
        for line in self:
            line.can_see_stock_central = not bool(self.env.user.property_warehouse_id)

    @api.depends('stock_central', 'request_id.state', 'qty_request') # <-- DEPENDENCIA AÑADIDA
    @api.depends_context('uid')
    def _compute_show_red_alert(self):
        is_sala_user = self.user_has_groups('parches_insumar.group_sala')
        for line in self:
            line.show_red_alert = (
                not is_sala_user and
                line.request_id.state == 'review' and
                (line.stock_central == 0 or line.qty_request > line.stock_central) # <-- CONDICIÓN MODIFICADA
            )

    @api.depends('product_id', 'request_id.warehouse_id')
    def _compute_stock_info(self):
        central_warehouse = self.env['stock.warehouse'].search([('code', '=', 'WH')], limit=1)
        
        for line in self:
            if not line.product_id:
                line.stock_branch = 0
                line.stock_central = 0
                continue

            line.stock_branch = line.product_id.with_context(warehouse=line.request_id.warehouse_id.id).virtual_available

            if central_warehouse:
                line.stock_central = line.product_id.with_context(warehouse=central_warehouse.id).virtual_available
            else:
                line.stock_central = 0

    @api.depends('product_id')
    def _compute_avg_sales(self):
        for line in self:
            if not line.product_id:
                line.avg_sales_3m = 0
                continue
            
            from_date = fields.Datetime.now() - relativedelta(days=90)
            sales_data = self.env['sale.report'].read_group(
                domain=[
                    ('product_id', '=', line.product_id.id), 
                    ('date', '>=', from_date),
                    ('warehouse_id', '=', line.request_id.warehouse_id.id)
                ],
                fields=['product_uom_qty'],
                groupby=[]
            )
            total_sales = sales_data[0].get('product_uom_qty') or 0.0 if sales_data else 0.0
            line.avg_sales_3m = total_sales / 3.0 if total_sales > 0 else 0.0