import pytest
import os
from maude_hcs.parsers.quatexGenerator import QuatexGenerator

@pytest.fixture
def full_template_content():
    """Returns the content of the full adversary_param.j2 for testing."""
    return """
// Adversary Parameter Template
// k = {{ k }}
// w = {{ w }}
ToDAvgQPS() = if (s.rval("getToD(C,0.0,{{ w }},{{ s }},{{ k }},{{ n }})") == 0.0) then discard else s.rval("getToD(C,0.0,{{ w }},{{ s }},{{ k }},{{ n }})") fi;
// C.1 Check
ToDCumulativeNQueryPreNAT() = if (s.rval("getToDCumulativeNQueryPreNAT(C,N)") == 0.0) then discard
"""

@pytest.fixture
def setup_generator(tmp_path, full_template_content):
    """Creates a temporary template file and initializes the generator."""
    d = tmp_path / "templates"
    d.mkdir()
    p = d / "test_adversary.j2"
    p.write_text(full_template_content)
    return QuatexGenerator(str(p)), d

def test_generate_quatex_logic(setup_generator, tmp_path):
    """
    Verifies that variables are substituted correctly and w is calculated as s*m.
    """
    generator, _ = setup_generator
    output_file = tmp_path / "generated_adversary.quatex"
    
    # Define Inputs
    k_val = 1.5
    n_val = 4
    s_val = 20
    m_val = 3
    # Expected w = 20 * 3 = 60
    
    # Execution
    content = generator.generate_file(
        k=k_val,
        n=n_val,
        s=s_val,
        m=m_val,
        output_filename=str(output_file)
    )
    
    # Verification
    assert output_file.exists()
    
    # 1. Check Derived Variable w calculation
    # "getToD(..., 60, ...)"
    assert f"getToD(C,0.0,60,{s_val},{k_val},{n_val})" in content
    
    # 2. Check Static Content Preservation
    # Ensure parts of the file that shouldn't change remained intact
    assert "ToDCumulativeNQueryPreNAT" in content
    assert "(C,N)" in content  # N should NOT be replaced
    
    # 3. Check variable replacement in comments if they exist in template
    # "// k = 1.5"
    assert f"// k = {k_val}" in content

def test_generate_file_structure(tmp_path):
    """
    Integration test using the actual file content logic if available,
    or ensuring the file write works for any string content.
    """
    # Create a simple template just for this test
    tpl_path = tmp_path / "simple.j2"
    tpl_path.write_text("Value: {{ w }}")
    
    gen = QuatexGenerator(str(tpl_path))
    out_path = tmp_path / "simple.out"
    
    gen.generate_file(1, 1, 10, 5, str(out_path)) # w=50
    
    assert out_path.read_text() == "Value: 50"
