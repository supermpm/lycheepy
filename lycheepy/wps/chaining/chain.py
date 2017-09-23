import json
from datetime import datetime

import networkx as nx
from pywps.app.Common import Metadata

from simplyrestful.database import session

from lycheepy.utils import DefaultDict
from lycheepy.settings import PROCESS_EXECUTION_TIMEOUT
from lycheepy.models import Execution
from lycheepy.wps.service import ProcessesGateway
from lycheepy.wps.chaining.publisher_process import PublisherProcess
from lycheepy.wps.chaining.distribution.broker import run_process
from lycheepy.wps.chaining.distribution.serialization import OutputsSerializer


class Chain(PublisherProcess):
    def __init__(self, model):
        self.model = model

        self.graph = self._build_graph()

        self.match = self._get_match()
        self.products = self._get_products()

        self.execution = None

        super(Chain, self).__init__(
            self._handle,
            self.model.identifier,
            self.model.title,
            abstract=self.model.abstract,
            version=self.model.version,

            inputs=self._get_inputs(),
            outputs=self._get_outputs(),

            metadata=self._get_metadata(),

            # Check if all the involved processes support it?
            # Or only the ones that provide the chain outputs?
            store_supported=True,

            status_supported=True
        )

    def _get_inputs(self):
        return [
            process_input
            for process in self._get_nodes_without_predecessors()
            for process_input in ProcessesGateway.get(process).inputs
        ]

    def _get_outputs(self):
        return [
            process_output
            for process in self._get_nodes_without_successors()
            for process_output in ProcessesGateway.get(process).outputs
        ]

    def _get_nodes_without_predecessors(self):
        return [node for node, degree in self.graph.in_degree_iter() if degree is 0]

    def _get_nodes_without_successors(self):
        return [node for node, degree in self.graph.in_degree_iter() if len(self.graph.successors(node)) is 0]

    def _get_metadata(self):
        return [Metadata(metadata.value) for metadata in self.model.meta_data]

    def _build_graph(self):
        g = nx.DiGraph()
        for step in self.model.steps:
            g.add_edge(step.before.identifier, step.after.identifier)
        return g

    def _get_match(self):
        match = DefaultDict()
        for step in self.model.steps:
            before = step.before.identifier
            after = step.after.identifier
            for match in step.matches:
                output = match.output.identifier
                input_identifier = match.input.identifier
                self.match[after][before][output] = input_identifier
        return match

    def _get_products(self):
        products = dict()
        for step in self.model.steps:
            for output in step.publishables:
                process = output.process.identifier
                if process not in products:
                    products[process] = []
                products[process].append(output.identifier)
        return products

    @property
    def anti_chain(self):
        anti_chain = [a[0] if len(a) == 1 else a for a in list(nx.antichains(self.graph))]
        anti_chain.pop(0)
        return list(
            reversed(
                [
                    a for a in anti_chain
                    if a not in [
                        c for b in anti_chain
                        if type(b) is list
                        for c in b
                    ]
                ]
            )
        )

    def _handle(self, wps_request, wps_response):
        outputs = dict()

        self._begin_execution()

        for level in self.anti_chain:
            results = dict()

            processes = level if type(level) is list else [level]

            # TODO: Use Celery groups or chains (chains would include publishing)
            for process in processes:
                results[process] = self.run_process(process, json.loads(wps_request.json), outputs)

            for process in processes:
                outputs[process] = results[process].get(PROCESS_EXECUTION_TIMEOUT)

            # Publish. TODO: Define where it should be done. In the celery task?
            # Yes. In the Celery task, to run publication in parallel
            for process in processes:
                self.publish(process, outputs[process])

        self.set_outputs_values(wps_response, outputs)

        self._end_execution()

        return wps_response

    def _begin_execution(self):
        self.execution = Execution(chain=self.model, id=self.uuid, status=Execution.PROCESSING)
        session.add(self.execution)

    def _end_execution(self):
        self.execution.status = Execution.SUCCESS
        self.execution.end = datetime.now()
        session.add(self.execution)

    def run_process(self, process, request_json, outputs):
        request_json['identifiers'] = [process]

        if process not in self._get_nodes_without_predecessors():
            request_json['inputs'] = self.get_process_inputs(outputs, process)

        return run_process.delay(process, json.dumps(request_json))

    def get_process_inputs(self, outputs, p):
        inputs = {}
        for s in self.graph.predecessors(p):
            for k, output in outputs[s].iteritems():
                input_name = self.match[p][s][k] if k in self.match[p][s] else k
                inputs[input_name] = output
        return inputs

    def set_outputs_values(self, wps_response, execution_outputs):
        for process in self._get_nodes_without_successors():
            for output in ProcessesGateway.get(process).outputs:
                output_identifier = output.identifier
                OutputsSerializer.add_data(
                    execution_outputs[process][output_identifier][0],  # TODO: Handle outputs with multiple occurrences
                    wps_response.outputs[output_identifier]
                )

    def publish(self, process, outputs):
        m = {
            'application/x-ogc-wcs; version=2.0': 'publish_raster',
            'application/gml+xml': 'publish_features'
        }
        if process in self.products:
            for product in self.products[process]:
                for output in outputs[product]:
                    mime_type = output['data_format']['mime_type']
                    if mime_type in m:
                        product_identifier = '{}:{}:{}'.format(process, self.uuid, product)
                        getattr(self.get_repository(), m[mime_type])(
                            self,
                            product_identifier,
                            output['file']
                        )

    # TODO: Chain class should be abstract? And implement this method in child classes
    def get_repository(self):
        from publishing.geo_server_repository import GeoServerRepository
        return GeoServerRepository()