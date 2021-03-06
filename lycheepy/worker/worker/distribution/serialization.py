from pywps.inout.outputs import ComplexOutput


class OutputsSerializer(object):

    @staticmethod
    def to_json(outputs):
        outputs_json = dict()

        for identifier, output in outputs.iteritems():

            # Common properties
            output_json = dict(
                workdir=output.workdir,
                identifier=output.identifier,
                title=output.title,
                abstract=output.abstract,
                mode=output.valid_mode
            )

            if isinstance(output, ComplexOutput):
                additional_properties = dict(
                    type='complex',
                    file=output.file,
                    source=output.source,
                    data_format=output.data_format.json,
                    supported_formats=[f.json for f in output.supported_formats],
                    data=output.data if not output.as_reference else None,
                    as_reference=output.as_reference
                )
            else:
                additional_properties = dict(
                    type='literal',
                    data=output.data,
                    data_type=output.data_type,
                    allowed_values=[],  # TODO
                    uoms=output.uoms,
                    uom=None,  # TODO
                )

            output_json.update(additional_properties)

            if identifier not in outputs_json:
                outputs_json[identifier] = []

            outputs_json[identifier].append(output_json)

        return outputs_json
