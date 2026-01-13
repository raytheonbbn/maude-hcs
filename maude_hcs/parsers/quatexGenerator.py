import os
from jinja2 import Environment, FileSystemLoader


class QuatexGenerator:
    """
    Handles the ingestion of a Jinja2 template and generation of
    concrete Quatex files based on provided configuration.
    """

    def __init__(self, template_path):
        """
        Initialize the generator with the path to the jinja2 template.

        Args:
            template_path (str): Full path or relative path to the .j2 file.
        """
        self.template_path = template_path
        self.template_dir = os.path.dirname(os.path.abspath(template_path))
        self.template_name = os.path.basename(template_path)

        # Initialize Jinja2 Environment
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        self.template = self.env.get_template(self.template_name)

    def generate_file(self, config, output_filename):
        """
        Generates a quatex file with replaced variables based on groups.

        Args:
            config (dict): A dictionary containing keys for each query type:
                           'qps', 'qsize', 'respsize', 'uploadrate'.
                           Can also include a top-level 'start_time' key.
                           Can also include cumulative threshold keys (N_...).
            output_filename (str): Path to write the generated file.

        Returns:
            str: The content that was written to the file.
        """
        context = {}

        # Extract global start_time, default to 0.0 if not provided
        start_time = config.get('start_time', 0.0)
        context['start_time'] = start_time

        required_groups = ['qps', 'qsize', 'respsize', 'uploadrate']

        for group in required_groups:
            if group not in config:
                raise ValueError(f"Configuration missing required group: {group}")

            params = config[group]

            # Extract basic params
            k = params['k']
            n = params['n']
            s = params['s']
            m = params['m']

            # Calculate derived param w
            w = s * m

            # Add to context with suffix
            context[f'k_{group}'] = k
            context[f'n_{group}'] = n
            context[f's_{group}'] = s
            context[f'm_{group}'] = m
            context[f'w_{group}'] = w

        # Add cumulative threshold parameters directly to context
        cumulative_keys = [
            'N_query_pre_nat', 'N_query_post_nat',
            'N_query_size_pre_nat', 'N_query_size_post_nat',
            'N_response_pre_nat', 'N_response_post_nat',
            'N_http_conn_pre_nat', 'N_http_conn_post_nat',
            'N_http_upload_pre_nat', 'N_http_upload_post_nat'
        ]

        for key in cumulative_keys:
            # We don't error if missing, just pass if present;
            # Jinja will handle missing vars (empty string) or error depending on env settings.
            if key in config:
                context[key] = config[key]

        # Render the template with the provided context
        rendered_content = self.template.render(**context)

        # Write the rendered content to the output file
        with open(output_filename, 'w') as f:
            f.write(rendered_content)

        print(f"Successfully generated {output_filename}")
        return rendered_content
