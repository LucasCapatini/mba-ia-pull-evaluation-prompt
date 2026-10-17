"""
Script para fazer pull de prompts do LangSmith Prompt Hub.

Este script:
1. Conecta ao LangSmith usando LANGSMITH_API_KEY do .env
2. Faz pull do prompt semente do desafio (leonanluppi/bug_to_user_story_v1)
3. Converte o ChatPromptTemplate retornado em um dicionário no formato do YAML v1
   (system_prompt, user_prompt, version, tags), lendo `prompt.messages` e o
   atributo `.prompt.template` de cada mensagem
4. Salva localmente em prompts/bug_to_user_story_v1.yml com `save_yaml` de utils.py

Observação sobre `dangerously_pull_public_prompt=True`: o parâmetro é obrigatório
sempre que o identificador tem dono explícito ("owner/nome"). O LangSmith bloqueia
esse pull por padrão porque um prompt do Hub é um objeto LangChain serializado,
que pode vir de terceiros. Aqui o prompt é o do desafio, então o risco é conhecido.

Uso (a partir da raiz do repositório, com o venv ativo):
    python src/pull_prompts.py
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from langsmith import Client
from langchain_core.prompts import ChatPromptTemplate
from utils import save_yaml, check_env_vars, print_section_header

load_dotenv()

# Prompt semente do desafio (publicado pelo autor do repositório base)
SEED_PROMPT_ID = "leonanluppi/bug_to_user_story_v1"

# Nome da chave raiz no YAML e do arquivo de saída
LOCAL_PROMPT_NAME = "bug_to_user_story_v1"
OUTPUT_PATH = Path("prompts") / f"{LOCAL_PROMPT_NAME}.yml"

# Mapeia o tipo de mensagem do LangChain para o campo do YAML
ROLE_TO_FIELD = {
    "system": "system_prompt",
    "human": "user_prompt",
    "ai": "assistant_prompt",
}


def _message_role(message: Any) -> str:
    """
    Descobre o papel (system/human/ai) de um template de mensagem.

    Os templates do LangChain não expõem um campo "role" direto, mas o nome
    da classe segue o padrão SystemMessagePromptTemplate, HumanMessagePromptTemplate etc.
    """
    class_name = type(message).__name__.lower()
    for role in ROLE_TO_FIELD:
        if class_name.startswith(role):
            return role
    return "unknown"


def _message_template(message: Any) -> Optional[str]:
    """Extrai o texto do template de uma mensagem, se existir."""
    inner = getattr(message, "prompt", None)
    template = getattr(inner, "template", None)
    if isinstance(template, str):
        return template
    return None


def prompt_to_dict(prompt: ChatPromptTemplate, hub_id: str) -> Dict[str, Any]:
    """
    Converte o ChatPromptTemplate puxado do Hub no mesmo formato do YAML v1.

    O formato mantém os campos que o desafio usa (description, system_prompt,
    user_prompt, version, tags) e acrescenta informações do Hub úteis para
    rastreabilidade (origem, commit e variáveis de entrada).
    """
    data: Dict[str, Any] = {
        "description": "Prompt para converter relatos de bugs em User Stories",
    }

    for message in prompt.messages:
        role = _message_role(message)
        template = _message_template(message)
        field = ROLE_TO_FIELD.get(role)

        if field is None or template is None:
            print(f"   ⚠️  Mensagem ignorada (tipo não suportado): {type(message).__name__}")
            continue

        data[field] = template

    hub_metadata = prompt.metadata or {}

    data.update({
        "version": "v1",
        "source": hub_id,
        "hub_commit": hub_metadata.get("lc_hub_commit_hash", ""),
        "input_variables": list(prompt.input_variables),
        "tags": ["bug-analysis", "user-story", "product-management"],
    })

    return data


def pull_prompts_from_langsmith() -> bool:
    """
    Faz pull do prompt semente do Hub e grava em prompts/bug_to_user_story_v1.yml.

    Returns:
        True se o arquivo foi gravado, False caso contrário.
    """
    client = Client()

    print(f"Puxando prompt do LangSmith Hub: {SEED_PROMPT_ID}")

    try:
        prompt = client.pull_prompt(SEED_PROMPT_ID, dangerously_pull_public_prompt=True)
    except Exception as e:
        print(f"❌ Erro ao fazer pull do prompt '{SEED_PROMPT_ID}': {e}")
        print("\nVerifique:")
        print("- LANGSMITH_API_KEY está configurada corretamente no .env")
        print("- O prompt existe e é público em https://smith.langchain.com/hub")
        return False

    if not isinstance(prompt, ChatPromptTemplate):
        print(f"❌ O objeto retornado não é um ChatPromptTemplate: {type(prompt).__name__}")
        return False

    print(f"   ✓ Prompt carregado ({len(prompt.messages)} mensagens)")
    print(f"   ✓ Variáveis de entrada: {prompt.input_variables}")

    prompt_dict = prompt_to_dict(prompt, SEED_PROMPT_ID)

    if "system_prompt" not in prompt_dict:
        print("⚠️  O prompt não tem mensagem de sistema; o YAML ficará sem system_prompt.")

    payload = {LOCAL_PROMPT_NAME: prompt_dict}

    if not save_yaml(payload, str(OUTPUT_PATH)):
        return False

    print(f"   ✓ Prompt salvo em {OUTPUT_PATH}")

    print("\nConteúdo do system_prompt:")
    print("-" * 50)
    print(prompt_dict.get("system_prompt", "(vazio)"))
    print("-" * 50)
    print(f"user_prompt: {prompt_dict.get('user_prompt', '(vazio)')!r}")

    return True


def main():
    """Função principal"""
    print_section_header("PULL DE PROMPTS DO LANGSMITH HUB")

    if not check_env_vars(["LANGSMITH_API_KEY"]):
        return 1

    if not pull_prompts_from_langsmith():
        return 1

    print("\n✅ Pull concluído!")
    print("\nPróximos passos:")
    print(f"1. Analise o prompt em {OUTPUT_PATH}")
    print("2. Crie a versão otimizada em prompts/bug_to_user_story_v2.yml")
    print("3. Faça push: python src/push_prompts.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
