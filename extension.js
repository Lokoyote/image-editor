import GObject from 'gi://GObject';
import St from 'gi://St';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const Indicator = GObject.registerClass(
class Indicator extends PanelMenu.Button {
    _init(extensionPath) {
        super._init(0.0, 'Image Editor');
        this._extensionPath = extensionPath;

        const icon = new St.Icon({
            icon_name: 'applets-screenshooter-symbolic',
            style_class: 'system-status-icon',
        });
        this.add_child(icon);

        const openItem = new PopupMenu.PopupMenuItem('Open an Image to Edit…');
        openItem.connect('activate', () => this._launchEditor());
        this.menu.addMenuItem(openItem);
    }

    _pythonBin() {
        // Use the system's python3; the app handles its own GTK4 imports.
        return 'python3';
    }

    _launchEditor() {
        try {
            const scriptPath = GLib.build_filenamev([this._extensionPath, 'image-editor.py']);

            if (!GLib.file_test(scriptPath, GLib.FileTest.EXISTS)) {
                Main.notifyError('Image Editor', `Script not found: ${scriptPath}`);
                return;
            }

            const argv = [this._pythonBin(), scriptPath];

            const proc = new Gio.Subprocess({
                argv,
                flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
            });
            proc.init(null);


            proc.communicate_utf8_async(null, null, (p, res) => {
                try {
                    const [, stdout, stderr] = p.communicate_utf8_finish(res);
                    const status = p.get_exit_status();
                    if (status !== 0) {
                        const msg = (stderr && stderr.trim()) || (stdout && stdout.trim()) ||
                            `exit code ${status}`;
                        logError(new Error(msg), 'image-editor.py failed');
                        Main.notifyError('Image Editor',
                            `Failed to launch. Details:\n${msg.slice(0, 400)}`);
                    }
                } catch (e) {
                    logError(e, 'Error reading image-editor.py output');
                }
            });
        } catch (e) {
            Main.notifyError('Image Editor', `Couldn't launch the editor: ${e.message}`);
        }
    }
});

export default class ImageEditorExtension extends Extension {
    enable() {
        this._indicator = new Indicator(this.path);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
