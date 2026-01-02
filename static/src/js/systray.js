odoo.define('insumar_sp.SystrayMenu', function (require) {
    "use strict";

    const { Component, useState } = owl;
    const { useService } = require("@web/core/utils/hooks"); // Importación correcta en Odoo 16
    const { registry } = require("@web/core/registry");

    class InsumarSpMenu extends Component {
        setup() {
            this.rpc = useService("rpc");
            this.actionService = useService("action");
            
            // Usamos useState para que la vista reaccione automáticamente al cambio
            this.state = useState({ counter: 0 });
            
            this.updateCounter();
            
            // Polling cada 60 segundos
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
            // No necesitamos llamar render() manualmente con useState
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

    // Asignamos el template XML
    InsumarSpMenu.template = 'insumar_sp.SystrayMenu';
    
    // Registramos el widget en el menú del sistema (Systray) de Odoo 16
    registry.category("systray").add("insumar_sp.SystrayMenu", InsumarSpMenu, { sequence: 1 });

    return InsumarSpMenu;
});