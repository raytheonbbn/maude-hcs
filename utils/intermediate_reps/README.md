# Proto-IR: DSL Protocol Modeler

Proto-IR is a Python-based compiler, testing simulator, and transpiler designed for architecting conceptual protocol interactions and State Machines using a streamlined Domain Specific Language (DSL). It supports natively translating structural models to `.maude` format for formal verification properties.

## Prerequisites
- Python 3.8+
- [Optional] `graphviz` installed on your host system (required for `-g` flag to generate graph PNGs). e.g `brew install graphviz` on macOS.

## Environment Setup
It is highly recommended to run this tool inside a Python Virtual Environment to keep dependencies isolated:

1. Create a new virtual environment:
```bash
python3 -m venv venv
```

2. Activate the virtual environment:
```bash
# On Linux / macOS
source venv/bin/activate

# On Windows
venv\Scripts\activate
```

3. Install requirements using `pip`:
```bash
pip install -r requirements.txt
```

### CLI Options
- `FILE`: The entrypoint module (supports internally resolving `import "..."` syntax files in the same directory path hierarchy)
- `-c`, `--config`: YAML/JSON configuration specifying parameters
- `-o`, `--output-file`: The destination path of the generated `.maude` output program
- `-g`, `--graph`: Attempts to invoke `graphviz` to visualize a `.graph_0.png` rendering the abstract graph of Machine states

### Execution
Run the compiler from the project root:

```bash
python3 transpile.py irc/main.model -c irc/config.yaml -o irc_maude
```
### Running Maude
To interactively load the structural schemas into the Maude interpreter for manual formal reduction and verification, simply invoke:
```bash
maude irc_maude/index.maude
```
