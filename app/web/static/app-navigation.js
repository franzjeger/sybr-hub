// The shell interface. main.js wires it once, before authentication or view events.
// Features depend on this interface, so the shell can compose features without cycles.
var _navigation = null;
export function configureNavigation(actions) {
  if (_navigation) throw new Error('Navigation is already configured');
  var required = ["showView", "showNetworkTab", "syncRoute", "checkAuth", "passwordMeetsRule", "applyWriteCapability", "applyFeatureVisibility", "renderToolCustomerPickers", "toolCustomerId", "_syncConnChip", "setVpnTunnelUp", "toggleCommandPalette", "dashLoadAlerts", "overviewSelectCustomer", "loadCustomers", "dashLoadArchive", "openAdmin", "openCustomerPage"];
  required.forEach(function(name) { if (typeof actions[name] !== 'function') throw new Error('Missing navigation action: ' + name); });
  _navigation = Object.freeze(actions);
}
export function navShowView(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.showView(...args); }
export function navShowNetworkTab(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.showNetworkTab(...args); }
export function navSyncRoute(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.syncRoute(...args); }
export function navCheckAuth(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.checkAuth(...args); }
export function navPasswordMeetsRule(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.passwordMeetsRule(...args); }
export function navApplyWriteCapability(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.applyWriteCapability(...args); }
export function navApplyFeatureVisibility(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.applyFeatureVisibility(...args); }
export function navRenderToolCustomerPickers(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.renderToolCustomerPickers(...args); }
export function navToolCustomerId(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.toolCustomerId(...args); }
export function navSyncConnChip(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation._syncConnChip(...args); }
export function navSetVpnTunnelUp(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.setVpnTunnelUp(...args); }
export function navToggleCommandPalette(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.toggleCommandPalette(...args); }
export function navDashLoadAlerts(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.dashLoadAlerts(...args); }
export function navOverviewSelectCustomer(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.overviewSelectCustomer(...args); }
export function navLoadCustomers(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.loadCustomers(...args); }
export function navDashLoadArchive(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.dashLoadArchive(...args); }
export function navOpenAdmin(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.openAdmin(...args); }
export function navOpenCustomerPage(...args) { if (!_navigation) throw new Error('Navigation is not configured'); return _navigation.openCustomerPage(...args); }
