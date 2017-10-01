from repository import Repository
from geoserver.catalog import Catalog


class GeoServerRepository(Repository):

    def __init__(self, protocol, host, port, path='geoserver/rest', username='admin', password='geoserver', workspace='lycheepy'):
        self.url = '{}://{}:{}'.format(protocol, host, port)
        self.catalog = Catalog('{}/{}'.format(self.url, path), username=username, password=password)
        self.workspace = self._get_workspace(workspace)

    def _get_workspace(self, workspace):
        workspace = self.catalog.get_workspace(workspace)
        if not workspace:
            workspace = self.catalog.create_workspace(workspace, workspace)
        return workspace

    def publish_raster(self, name, raster_file):
        self.catalog.create_coveragestore(name, raster_file, self.workspace, True)
        return '{}/geoserver/wcs?SERVICE=WCS&REQUEST=GetCoverage&VERSION=2.0.1&CoverageId={}'.format(
            self.url, name
        )

    def publish_features(self, name, features_file): raise NotImplementedError