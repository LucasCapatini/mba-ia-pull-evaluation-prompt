"""
Testes automatizados para validação de prompts.
"""
import re
import pytest
import yaml
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils import validate_prompt_structure

PROMPTS_FILE = Path(__file__).parent.parent / "prompts" / "bug_to_user_story_v2.yml"


def load_prompts(file_path: str):
    """Carrega prompts do arquivo YAML."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def prompts():
    """Todos os prompts do arquivo v2 (chave raiz -> dados do prompt)."""
    assert PROMPTS_FILE.exists(), f"Arquivo não encontrado: {PROMPTS_FILE}"
    data = load_prompts(str(PROMPTS_FILE))
    assert isinstance(data, dict) and data, "O YAML deve ter ao menos um prompt na raiz"
    return data


@pytest.fixture(scope="module")
def prompt_data(prompts):
    """Dados do prompt otimizado bug_to_user_story_v2."""
    assert "bug_to_user_story_v2" in prompts, "Chave raiz 'bug_to_user_story_v2' não encontrada"
    return prompts["bug_to_user_story_v2"]


@pytest.fixture(scope="module")
def full_text(prompt_data):
    """system_prompt + user_prompt concatenados, para buscas textuais."""
    return f"{prompt_data.get('system_prompt', '')}\n{prompt_data.get('user_prompt', '')}"


class TestPrompts:
    def test_prompt_has_system_prompt(self, prompt_data):
        """Verifica se o campo 'system_prompt' existe e não está vazio."""
        assert "system_prompt" in prompt_data, "Campo 'system_prompt' ausente"
        system_prompt = prompt_data["system_prompt"]
        assert isinstance(system_prompt, str), "'system_prompt' deve ser texto"
        assert system_prompt.strip(), "'system_prompt' está vazio"

    def test_prompt_has_role_definition(self, prompt_data):
        """Verifica se o prompt define uma persona (ex: "Você é um Product Manager")."""
        system_prompt = prompt_data["system_prompt"]
        pattern = r"(você é um|você é uma|atue como|assuma o papel de|sua especialidade)"
        assert re.search(pattern, system_prompt, re.IGNORECASE), \
            "O system_prompt não define uma persona (ex.: 'Você é um Product Owner...')"

    def test_prompt_mentions_format(self, full_text):
        """Verifica se o prompt exige formato Markdown ou User Story padrão."""
        mentions_user_story = re.search(r"user story", full_text, re.IGNORECASE)
        mentions_template = re.search(
            r"como um.*?eu quero.*?para que", full_text, re.IGNORECASE | re.DOTALL
        )
        mentions_criteria = re.search(r"critérios de aceitação", full_text, re.IGNORECASE)
        mentions_markdown = re.search(r"markdown", full_text, re.IGNORECASE)

        assert mentions_user_story and mentions_template, \
            "O prompt deve exigir o formato de User Story 'Como um..., eu quero..., para que...'"
        assert mentions_criteria or mentions_markdown, \
            "O prompt deve descrever o formato da saída (Critérios de Aceitação ou Markdown)"

    def test_prompt_has_few_shot_examples(self, prompt_data):
        """Verifica se o prompt contém exemplos de entrada/saída (técnica Few-shot)."""
        system_prompt = prompt_data["system_prompt"]

        examples = re.findall(r"exemplo\s*\d+", system_prompt, re.IGNORECASE)
        assert len(examples) >= 2, \
            f"Esperado ao menos 2 exemplos few-shot, encontrados: {len(examples)}"

        inputs = re.findall(r"^\s*entrada:", system_prompt, re.IGNORECASE | re.MULTILINE)
        outputs = re.findall(r"^\s*saída esperada:", system_prompt, re.IGNORECASE | re.MULTILINE)
        assert len(inputs) >= 2 and len(outputs) >= 2, \
            "Cada exemplo deve ter um par 'Entrada:' / 'Saída esperada:'"
        assert len(inputs) == len(outputs), \
            "Quantidade de entradas e saídas dos exemplos não confere"

    def test_prompt_no_todos(self, prompt_data):
        """Garante que você não esqueceu nenhum `[TODO]` no texto."""
        # Sensível a maiúsculas, como em utils.validate_prompt_structure: o marcador é
        # "TODO"/"[TODO]"; a palavra "todos" em português não pode disparar o teste.
        for field in ("description", "system_prompt", "user_prompt"):
            value = prompt_data.get(field, "") or ""
            assert "TODO" not in value, f"O campo '{field}' ainda contém TODO"

    def test_minimum_techniques(self, prompt_data):
        """Verifica (através dos metadados do yaml) se pelo menos 2 técnicas foram listadas."""
        techniques = prompt_data.get("techniques_applied", [])
        assert isinstance(techniques, list), "'techniques_applied' deve ser uma lista"
        assert len(techniques) >= 2, \
            f"Mínimo de 2 técnicas requeridas, encontradas: {len(techniques)}"
        assert "few-shot" in [t.lower() for t in techniques], \
            "Few-shot Learning é obrigatório e deve estar em 'techniques_applied'"

        is_valid, errors = validate_prompt_structure(prompt_data)
        assert is_valid, f"Estrutura do prompt inválida: {errors}"

    def test_prompt_uses_only_bug_report_variable(self, prompt_data):
        """Garante que o template expõe exatamente a variável {bug_report} e só no user_prompt."""
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_data["system_prompt"]),
            ("user", prompt_data["user_prompt"]),
        ])
        assert sorted(prompt.input_variables) == ["bug_report"], \
            f"Variáveis inesperadas no template: {prompt.input_variables}"
        assert "{bug_report}" not in prompt_data["system_prompt"], \
            "{bug_report} deve aparecer apenas no user_prompt (no v1 estava duplicado)"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
