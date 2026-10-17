"""
Script para fazer push de prompts otimizados ao LangSmith Prompt Hub.

Este script:
1. Lê os prompts otimizados de prompts/bug_to_user_story_v2.yml com `load_yaml`
   (cada chave raiz do YAML é um prompt; o nome da chave vira o nome no Hub)
2. Valida cada prompt com `validate_prompt_structure` de utils.py, mais duas
   checagens locais: ausência de TODO no user_prompt e presença de {bug_report}
3. Monta um ChatPromptTemplate (system + user) e confere que a única variável de
   entrada é {bug_report}, a chave de inputs do dataset de avaliação
4. Faz push PÚBLICO para {USERNAME_LANGSMITH_HUB}/{nome}, com descrição e tags
   (as técnicas listadas em techniques_applied entram como tags)

Um novo push com conteúdo idêntico ao último commit não é tratado como erro: o
Hub recusa o commit vazio e o script informa que o prompt já está publicado.

USERNAME_LANGSMITH_HUB precisa ser o handle público do Hub, que só existe depois
de tornar algum prompt público pelo menos uma vez (instruções no .env.example).

Uso (a partir da raiz do repositório, com o venv ativo):
    python src/push_prompts.py
"""

import os
import sys
from typing import List
from dotenv import load_dotenv
from langsmith import Client
from langchain_core.prompts import ChatPromptTemplate
from utils import load_yaml, check_env_vars, print_section_header, validate_prompt_structure

load_dotenv()

PROMPTS_FILE = "prompts/bug_to_user_story_v2.yml"

# Única variável de entrada aceita: é a chave de inputs do dataset de avaliação
EXPECTED_INPUT_VARIABLES = ["bug_report"]


def build_chat_prompt(prompt_data: dict) -> ChatPromptTemplate:
    """
    Monta o ChatPromptTemplate a partir dos campos do YAML.

    O user_prompt é opcional: se ausente, o {bug_report} precisa estar no system_prompt.
    """
    messages = [("system", prompt_data["system_prompt"])]

    user_prompt = prompt_data.get("user_prompt")
    if user_prompt:
        messages.append(("user", user_prompt))

    return ChatPromptTemplate.from_messages(messages)


def build_tags(prompt_data: dict) -> List[str]:
    """Combina as tags do YAML com as técnicas aplicadas, sem duplicatas."""
    tags = list(prompt_data.get("tags", []))
    for technique in prompt_data.get("techniques_applied", []):
        if technique not in tags:
            tags.append(technique)
    return tags


def push_prompt_to_langsmith(prompt_name: str, prompt_data: dict) -> bool:
    """
    Faz push do prompt otimizado para o LangSmith Hub (PÚBLICO).

    Args:
        prompt_name: Nome do prompt
        prompt_data: Dados do prompt

    Returns:
        True se sucesso, False caso contrário
    """
    try:
        prompt = build_chat_prompt(prompt_data)
    except Exception as e:
        print(f"❌ Erro ao montar o ChatPromptTemplate: {e}")
        print("   Dica: chaves literais no texto precisam ser escapadas como {{ e }}.")
        return False

    input_variables = sorted(prompt.input_variables)
    if input_variables != EXPECTED_INPUT_VARIABLES:
        print(f"❌ Variáveis de entrada inválidas: {input_variables}")
        print(f"   O template precisa usar exatamente {EXPECTED_INPUT_VARIABLES}.")
        return False

    description = prompt_data.get("description", "")
    techniques = prompt_data.get("techniques_applied", [])
    if techniques:
        description = f"{description} | Técnicas: {', '.join(techniques)}"

    tags = build_tags(prompt_data)

    print(f"   Mensagens: {len(prompt.messages)} | Variáveis: {input_variables}")
    print(f"   Tags: {tags}")

    client = Client()

    try:
        url = client.push_prompt(
            prompt_name,
            object=prompt,
            is_public=True,
            description=description,
            tags=tags,
        )
        print(f"   ✓ Push concluído: {url}")
        return True

    except Exception as e:
        message = str(e).lower()

        # O Hub recusa um novo commit quando o conteúdo é idêntico ao último.
        # Nesse caso o prompt já está publicado, então não é uma falha.
        if "conflict" in message or "has not changed" in message or "nothing to commit" in message:
            print("   ✓ Prompt já está publicado com este conteúdo (nenhuma alteração desde o último push).")
            return True

        print(f"❌ Erro ao fazer push do prompt '{prompt_name}': {e}")
        print("\nVerifique:")
        print("- LANGSMITH_API_KEY está configurada corretamente no .env")
        print("- USERNAME_LANGSMITH_HUB é o seu handle público do Hub (ver .env.example)")
        print("- Você já tornou algum prompt público no LangSmith (isso cria o handle)")
        return False


def validate_prompt(prompt_data: dict) -> tuple[bool, list]:
    """
    Valida estrutura básica de um prompt (versão simplificada).

    Args:
        prompt_data: Dados do prompt

    Returns:
        (is_valid, errors) - Tupla com status e lista de erros
    """
    is_valid, errors = validate_prompt_structure(prompt_data)

    user_prompt = prompt_data.get("user_prompt", "") or ""
    if "TODO" in user_prompt:
        errors.append("user_prompt ainda contém TODOs")

    full_text = f"{prompt_data.get('system_prompt', '')}\n{user_prompt}"
    if "{bug_report}" not in full_text:
        errors.append("O prompt não usa a variável {bug_report}")

    return (len(errors) == 0, errors)


def main():
    """Função principal"""
    print_section_header("PUSH DE PROMPTS PARA O LANGSMITH HUB")

    if not check_env_vars(["LANGSMITH_API_KEY", "USERNAME_LANGSMITH_HUB"]):
        return 1

    username = os.getenv("USERNAME_LANGSMITH_HUB")

    prompts = load_yaml(PROMPTS_FILE)
    if not prompts:
        print(f"\nCrie o arquivo {PROMPTS_FILE} com o prompt otimizado antes de fazer push.")
        return 1

    all_ok = True

    for local_name, prompt_data in prompts.items():
        prompt_name = f"{username}/{local_name}"
        print(f"\n🔍 Validando: {local_name}")

        is_valid, errors = validate_prompt(prompt_data or {})
        if not is_valid:
            print("❌ Prompt inválido:")
            for error in errors:
                print(f"   - {error}")
            all_ok = False
            continue

        print("   ✓ Estrutura válida")
        print(f"\n🚀 Publicando: {prompt_name}")

        if not push_prompt_to_langsmith(prompt_name, prompt_data):
            all_ok = False

    if not all_ok:
        print("\n⚠️  Alguns prompts não foram publicados. Corrija os erros acima e rode novamente.")
        return 1

    print("\n✅ Todos os prompts foram publicados!")
    print("\nPróximos passos:")
    print("1. Confira em https://smith.langchain.com/prompts se o prompt está público")
    print("2. Execute a avaliação: python src/evaluate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
