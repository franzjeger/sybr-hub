import {t} from './app-i18n.js';
import {_currentUser, hasFeature} from './app-state.js';
import {_formatBytes} from './app-format.js';
import {apiFetch} from './app-api.js';
import {navSetVpnTunnelUp as setVpnTunnelUp, navSyncConnChip as _syncConnChip} from './app-navigation.js';

export async function _checkVpnHeaderBadge() {
  // Signed-out pages and accounts without the VPN feature have nothing to show
  // here, and the server refuses them.
  if (!_currentUser || !hasFeature('vpn')) return;
  try {
    var d = await apiFetch('/api/vpn/status');
    // Single status chip: prefix "VPN · " ahead of the live dot when a tunnel
    // is up (the old standalone #vpn-header-badge was merged into #conn-status).
    var prefix = document.getElementById('vpn-chip-prefix');
    if (!prefix) return;
    setVpnTunnelUp(!!(d && d.state === 'connected'));
    _syncConnChip();
    if (d && d.state === 'connected') {
      prefix.hidden = false;
      var stats = d.stats || {};
      var tip = 'VPN ' + t('vpn_connected','Connected');
      if (d.interface) tip += ' (' + d.interface + ')';
      if (stats.local_ip) tip += '\nIP: ' + stats.local_ip;
      if (stats.tx_bytes || stats.rx_bytes) tip += '\nTX: ' + _formatBytes(stats.tx_bytes||0) + ' / RX: ' + _formatBytes(stats.rx_bytes||0);
      tip += '\n' + t('tip_click_to_manage','Click to manage');
      prefix.title = tip;
    } else {
      prefix.hidden = true;
    }
  } catch(e) { /* VPN badge poll — retries every 30s */ }
}
