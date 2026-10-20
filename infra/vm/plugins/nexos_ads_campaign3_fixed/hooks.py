def install(): return None
def uninstall():
    try:
        from plugins._browser.helpers.runtime import _BrowserRuntimeCore
        for name in ("nexos_ads_campaign3_workflow",):
            if hasattr(_BrowserRuntimeCore, name): delattr(_BrowserRuntimeCore, name)
    except Exception: pass
