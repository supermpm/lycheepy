import json
from datetime import datetime

from simplyrestful.database import session

from lycheepy.models import Execution
from lycheepy.wps.service import ProcessesGateway
from lycheepy.wps.chaining.publisher_process import PublisherProcess
from lycheepy.wps.chaining.distribution.broker import run_processes
from lycheepy.wps.chaining.distribution.serialization import OutputsSerializer
from lycheepy.settings import PROCESS_EXECUTION_TIMEOUT


class Chain(PublisherProcess):
    def __init__(self, identifier, title, metadata, inputs, outputs, anti_chains, predecessors, successors, match, products, abstract='', version='None'):
        self.anti_chains = anti_chains
        self.predecessors = predecessors
        self.successors = successors
        self.match = match
        self.products = products
        super(Chain, self).__init__(
            self._handle,
            identifier,
            title,
            abstract=abstract,
            version=version,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            # Check if all the involved processes support it?
            # Or only the ones that provide the chain outputs?
            store_supported=True,
            status_supported=True
        )

    @property
    def without_predecessors(self):
        return [process for process, predecessors in self.predecessors.iteritems() if not predecessors]

    @property
    def without_successors(self):
        return [process for process, successors in self.successors.iteritems() if not successors]

    def _handle(self, wps_request, wps_response):
        outputs = dict()

        execution = self._begin_execution()

        for level in self.anti_chains:
            processes = level if type(level) is list else [level]

            self._load_outputs(
                run_processes(
                    self._get_processes_requests(
                        processes, wps_request, outputs
                    )
                ).get(PROCESS_EXECUTION_TIMEOUT),
                outputs
            )

            # Publish. TODO: Define where it should be done. In the celery task?
            # Yes. In the Celery task, to run publication in parallel
            for process in processes:
                self.publish(process, outputs[process])

        self._set_output_values(outputs, wps_response)

        self._end_execution(execution)

        return wps_response

    def _begin_execution(self):
        execution = Execution(chain_identifier=self.identifier, id=self.uuid, status=Execution.PROCESSING)
        session.add(execution)
        return execution

    def _end_execution(self, execution):
        execution.status = Execution.SUCCESS
        execution.end = datetime.now()
        session.add(execution)

    def _get_processes_requests(self, processes, wps_request, outputs):
        group = dict()
        for process in processes:
            request_json = json.loads(wps_request.json)
            request_json['identifiers'] = [process]
            request_json['inputs'] = self._get_process_inputs(process, request_json, outputs)
            group[process] = request_json
        return group

    def _get_process_inputs(self, process, request_json, outputs):
        inputs = request_json['inputs']
        if process not in self.without_predecessors:
            inputs = dict()
            for s in self.predecessors.get(process):
                for k, output in outputs[s].iteritems():
                    input_name = self.match[process][s][k] if k in self.match[process][s] else k
                    inputs[input_name] = output
        return inputs

    def _load_outputs(self, results, outputs):
        for result in results:
            outputs[result['process']] = result['output']

    def _set_output_values(self, outputs, wps_response):
        # TODO: Set values of extra-outputs
        for process in self.without_successors:
            for output in ProcessesGateway.get(process).outputs:
                output_identifier = output.identifier
                OutputsSerializer.add_data(
                    outputs[process][output_identifier][0],  # TODO: Handle outputs with multiple occurrences
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
