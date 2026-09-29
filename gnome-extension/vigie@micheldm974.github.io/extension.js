// Vigie : voile qui assombrit tous les écrans quand le service juge la posture mauvaise,
// et icône d'état dans la barre du haut (pause, ouverture de la page).
//
// Le service appelle Signaler(état, niveau) sur le bus de session, au moins toutes les
// 2 s. Sans nouvelles depuis SILENCE_MAX secondes, on considère le service arrêté et on
// retire le voile : un service planté ne doit jamais laisser l'écran sombre.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Soup from 'gi://Soup?version=3.0';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const CHEMIN_DBUS = '/io/github/micheldm974/Vigie';
const INTERFACE_DBUS = `
<node>
  <interface name="io.github.micheldm974.Vigie">
    <method name="Signaler">
      <arg type="s" direction="in" name="etat"/>
      <arg type="d" direction="in" name="niveau"/>
    </method>
  </interface>
</node>`;
const URL_SERVICE = 'http://127.0.0.1:8030';
const SILENCE_MAX = 6;  // secondes
const DUREE_TRANSITION = 900;  // ms

const LIBELLES = {
    ok: 'Bien droit',
    avachi: 'Avachi',
    absent: 'Personne devant la caméra',
    incertain: 'Mal cadré',
    pause: 'En pause, caméra libérée',
    non_calibre: 'Aucune posture de référence',
    sans_camera: 'Caméra indisponible',
    demarrage: 'Démarrage…',
    arret: 'Service arrêté',
};

const Indicateur = GObject.registerClass(
class Indicateur extends PanelMenu.Button {
    _init(extension) {
        super._init(0.0, 'Vigie');
        this._extension = extension;
        this._gicons = {
            normal: Gio.icon_new_for_string(`${extension.path}/icons/vigie-symbolic.svg`),
            pause: Gio.icon_new_for_string(`${extension.path}/icons/vigie-pause-symbolic.svg`),
        };
        this._icone = new St.Icon({gicon: this._gicons.normal, style_class: 'system-status-icon'});
        this.add_child(this._icone);

        this._libelle = new PopupMenu.PopupMenuItem('', {reactive: false});
        this.menu.addMenuItem(this._libelle);
        this._surveillance = new PopupMenu.PopupSwitchMenuItem('Surveillance', true);
        this._surveillance.connect('toggled', (_item, active) => extension.demanderPause(!active));
        this.menu.addMenuItem(this._surveillance);
        this._demarrer = new PopupMenu.PopupMenuItem('Démarrer le service');
        this._demarrer.connect('activate', () => extension.demarrerService());
        this.menu.addMenuItem(this._demarrer);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const ouvrir = new PopupMenu.PopupMenuItem('Ouvrir Vigie');
        ouvrir.connect('activate', () => Gio.AppInfo.launch_default_for_uri(`${URL_SERVICE}/`, null));
        this.menu.addMenuItem(ouvrir);
    }

    afficher(etat, niveau) {
        const arret = etat === 'arret';
        let libelle = LIBELLES[etat] ?? etat;
        if (niveau > 0)
            libelle += ` — écran assombri à ${Math.round(niveau * 100)} %`;
        this._libelle.label.text = libelle;
        this._icone.gicon = etat === 'pause' ? this._gicons.pause : this._gicons.normal;
        this._icone.style_class = `system-status-icon${
            etat === 'avachi' ? ' vigie-icone-avachi' : arret ? ' vigie-icone-arret' : ''}`;
        this._surveillance.setToggleState(etat !== 'pause');
        this._surveillance.setSensitive(!arret);
        this._demarrer.visible = arret;
    }
});

export default class VigieExtension extends Extension {
    enable() {
        this._etat = 'arret';
        this._niveau = 0;
        this._dernierSignal = 0;
        this._unredirectCoupe = false;
        this._session = new Soup.Session({timeout: 5});

        // Non réactif : les clics traversent le voile jusqu'aux fenêtres.
        this._voile = new St.Widget({
            style_class: 'vigie-voile', reactive: false, opacity: 0, visible: false,
        });
        this._voile.add_constraint(new Clutter.BindConstraint({
            source: global.stage, coordinate: Clutter.BindCoordinate.ALL,
        }));
        Main.uiGroup.add_child(this._voile);

        this._indicateur = new Indicateur(this);
        Main.panel.addToStatusArea(this.uuid, this._indicateur);
        this._indicateur.afficher(this._etat, 0);

        this._dbus = Gio.DBusExportedObject.wrapJSObject(INTERFACE_DBUS, this);
        this._dbus.export(Gio.DBus.session, CHEMIN_DBUS);

        this._surveillant = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            const silence = (GLib.get_monotonic_time() - this._dernierSignal) / 1e6;
            if (this._etat !== 'arret' && silence > SILENCE_MAX)
                this._appliquer('arret', 0);
            return GLib.SOURCE_CONTINUE;
        });
    }

    disable() {
        GLib.source_remove(this._surveillant);
        this._dbus.unexport();
        this._dbus = null;
        this._session.abort();
        this._session = null;
        this._retablirUnredirect();
        this._voile.destroy();
        this._voile = null;
        this._indicateur.destroy();
        this._indicateur = null;
    }

    // Méthode D-Bus, appelée par le service.
    Signaler(etat, niveau) {
        this._dernierSignal = GLib.get_monotonic_time();
        this._appliquer(etat, Math.min(Math.max(niveau, 0), 0.95));
    }

    _appliquer(etat, niveau) {
        const changement = etat !== this._etat || Math.abs(niveau - this._niveau) > 0.005;
        this._etat = etat;
        this._niveau = niveau;
        if (!changement)
            return;
        this._indicateur.afficher(etat, niveau);

        if (niveau > 0) {
            // Une fenêtre plein écran (vidéo, jeu) court-circuite la composition : on la
            // désactive le temps du voile, sinon il resterait invisible par-dessus.
            if (!this._unredirectCoupe) {
                global.compositor.disable_unredirect();
                this._unredirectCoupe = true;
            }
            Main.uiGroup.set_child_above_sibling(this._voile, null);
            this._voile.show();
        }
        this._voile.ease({
            opacity: Math.round(niveau * 255),
            duration: DUREE_TRANSITION,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onStopped: isFinished => {
                if (isFinished && this._niveau === 0 && this._voile) {
                    this._voile.hide();
                    this._retablirUnredirect();
                }
            },
        });
    }

    _retablirUnredirect() {
        if (this._unredirectCoupe) {
            global.compositor.enable_unredirect();
            this._unredirectCoupe = false;
        }
    }

    demanderPause(pause) {
        const message = Soup.Message.new('POST', `${URL_SERVICE}/api/pause`);
        const corps = new TextEncoder().encode(JSON.stringify({pause}));
        message.set_request_body_from_bytes('application/json', new GLib.Bytes(corps));
        this._session.send_and_read_async(message, GLib.PRIORITY_DEFAULT, null, (session, res) => {
            try {
                session.send_and_read_finish(res);
            } catch (e) {
                console.warn(`Vigie : pause impossible (${e.message})`);
            }
        });
    }

    demarrerService() {
        try {
            GLib.spawn_command_line_async('systemctl --user start vigie.service');
        } catch (e) {
            console.warn(`Vigie : démarrage impossible (${e.message})`);
        }
    }
}
