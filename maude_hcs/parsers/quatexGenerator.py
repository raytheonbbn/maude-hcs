import os
from jinja2 import Environment, FileSystemLoader


class QuatexGenerator:
    """
    Handles the ingestion of a Jinja2 template and generation of
    concrete Quatex files based on provided parameters.
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

    def generate_file(self, k, n, s, m, output_filename):
        """
        Generates a quatex file with replaced variables.

        Args:
            k (float/int): Threshold multiplier
            n (int): Number of consecutive bins
            s (float/int): Duration of each bin
            m (int): Number of previous bins to compute average over
            output_filename (str): Path to write the generated file

        Returns:
            str: The content that was written to the file.
        """
        # Calculate the derived variable w
        w = s * m

        # Render the template with the provided context
        # Note: N is not replaced here as it was not listed as a variable parameter
        # in the requirements, though it appears in C-sections of the template.
        rendered_content = self.template.render(
            k=k,
            n=n,
            s=s,
            m=m,
            w=w
        )

        # Write the rendered content to the output file
        with open(output_filename, 'w') as f:
            f.write(rendered_content)

        print(f"Successfully generated {output_filename} with w={w}")
        return rendered_content


if __name__ == "__main__":
    # Example usage
    generator = QuatexGenerator("adversary_param.j2")
    # Generates a file where w = 10 * 6 = 60
    generator.generate_file(k=2.5, n=5, s=10, m=6, output_filename="output_adversary.quatex")