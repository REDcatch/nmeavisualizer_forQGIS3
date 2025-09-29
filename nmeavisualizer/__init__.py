def classFactory(iface):
    from .plugin import NmeaVisualizerPlugin
    return NmeaVisualizerPlugin(iface)
