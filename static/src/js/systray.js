odoo.define('insumar_sp.SystrayMenu', function (require) {
    "use strict";

    const { Component } = owl;
    const { useService } = owl.hooks;
    const SystrayMenu = require('web.SystrayMenu');
    const { registry } = require('@web/core/registry');

    class InsumarSpMenu extends Component {
        setup() {
            this.rpc = useService('rpc');
            this.actionService = useService('action');
            this.state = { counter: 0 };
            this.updateCounter();
            
            // Consultar al servidor cada 60 segundos
            setInterval(() => {
                this.updateCounter();
            }, 60000);
        }

        async updateCounter() {
            const count = await this.rpc({
                model: 'insumar_sp.request',
                method: 'get_systray_sp_count',
            });
            this.state.counter = count;
            this.render(); // Re-renderizar para actualizar el número
        }

        _onClickSpRequests() {
            this.actionService.doAction({
                type: 'ir.actions.act_window',
                name: 'Solicitudes Pendientes',
                res_model: 'insumar_sp.request',
                views: [[false, 'tree'], [false, 'form']],
                domain: [['state', 'in', ['review', 'validated']]],
                target: 'current',
            });
        }
    }

    // Definir el template y los eventos
    InsumarSpMenu.template = 'insumar_sp.SystrayMenu';
    InsumarSpMenu.props = {};

    // Agregar al menú del sistema
    SystrayMenu.Items.push(InsumarSpMenu);

    return InsumarSpMenu;
});