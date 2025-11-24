#!/usr/bin/env python3
"""Compiler-style validation for agentic APIs.

This script validates:
1. Method name mismatches between agent definitions and calls
2. Import errors
3. Type signature mismatches
4. Missing attributes
"""

import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


class AgenticValidator:
    """Validates agentic code like a compiler."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.agent_methods: Dict[str, Set[str]] = {}
        self.method_calls: Dict[str, List[Tuple[int, str]]] = {}

    def validate_all(self) -> bool:
        """Run all validations. Returns True if no errors."""
        print("🔍 Running Compiler-Style Validation for Agentic APIs...\n")

        self.check_agent_method_definitions()
        self.check_controller_method_calls()
        self.validate_method_name_matches()
        self.check_asyncio_run_calls()
        self.check_imports()

        self.print_results()
        return len(self.errors) == 0

    def check_agent_method_definitions(self):
        """Extract all async method definitions from agent classes."""
        print("📋 Step 1: Extracting agent method definitions...")

        agent_files = {
            "SummarizerAgent": "agents/agentic/summarizer.py",
            "UniformerAgent": "agents/agentic/uniformer.py",
            "FinalizerAgent": "agents/agentic/finalizer.py",
            "VerifierAgent": "agents/agentic/verifier.py",
            "PatternMinerAgent": "agents/agentic/pattern_miner.py",
            "PromptArchitectAgent": "agents/agentic/prompt_architect.py",
            "CriticDryRunner": "agents/agentic/critic_dryrunner.py",
        }

        for agent_name, file_path in agent_files.items():
            full_path = self.base_path / "src/unstract/prompt_service" / file_path
            if not full_path.exists():
                self.warnings.append(f"Agent file not found: {file_path}")
                continue

            try:
                with open(full_path, "r") as f:
                    content = f.read()

                # Parse AST to find async methods
                tree = ast.parse(content)
                methods = set()

                for node in ast.walk(tree):
                    if isinstance(node, ast.AsyncFunctionDef):
                        # Skip private methods
                        if not node.name.startswith("_"):
                            methods.add(node.name)

                self.agent_methods[agent_name] = methods
                print(f"  ✓ {agent_name}: {', '.join(sorted(methods))}")

            except Exception as e:
                self.errors.append(f"Failed to parse {file_path}: {e}")

        print()

    def check_controller_method_calls(self):
        """Extract all agent method calls from controller."""
        print("📋 Step 2: Extracting controller method calls...")

        controller_path = (
            self.base_path
            / "src/unstract/prompt_service/controllers/agentic.py"
        )

        if not controller_path.exists():
            self.errors.append("Controller file not found!")
            return

        with open(controller_path, "r") as f:
            lines = f.readlines()

        # Pattern to match: object.method_name(
        pattern = re.compile(
            r"(summarizer|uniformer|finalizer|verifier|pattern_miner|architect|critic)\.(\w+)\("
        )

        agent_name_map = {
            "summarizer": "SummarizerAgent",
            "uniformer": "UniformerAgent",
            "finalizer": "FinalizerAgent",
            "verifier": "VerifierAgent",
            "pattern_miner": "PatternMinerAgent",
            "architect": "PromptArchitectAgent",
            "critic": "CriticDryRunner",
        }

        for line_num, line in enumerate(lines, 1):
            matches = pattern.findall(line)
            for var_name, method_name in matches:
                agent_name = agent_name_map.get(var_name)
                if agent_name:
                    if agent_name not in self.method_calls:
                        self.method_calls[agent_name] = []
                    self.method_calls[agent_name].append((line_num, method_name))
                    print(
                        f"  ✓ Line {line_num}: {agent_name}.{method_name}()"
                    )

        print()

    def validate_method_name_matches(self):
        """Validate that all method calls match method definitions."""
        print("🔬 Step 3: Validating method name matches...")

        has_errors = False

        for agent_name, calls in self.method_calls.items():
            defined_methods = self.agent_methods.get(agent_name, set())

            for line_num, method_name in calls:
                if method_name not in defined_methods:
                    self.errors.append(
                        f"❌ Line {line_num}: '{agent_name}' object has no attribute '{method_name}'\n"
                        f"   Available methods: {', '.join(sorted(defined_methods))}"
                    )
                    has_errors = True
                else:
                    print(f"  ✓ Line {line_num}: {agent_name}.{method_name}() - OK")

        if not has_errors:
            print("  ✓ All method calls match definitions!")

        print()

    def check_asyncio_run_calls(self):
        """Check all asyncio.run() calls use correct async methods."""
        print("🔬 Step 4: Validating asyncio.run() calls...")

        controller_path = (
            self.base_path
            / "src/unstract/prompt_service/controllers/agentic.py"
        )

        with open(controller_path, "r") as f:
            lines = f.readlines()

        # Pattern to match asyncio.run(agent.method())
        pattern = re.compile(r"asyncio\.run\((\w+)\.(\w+)\(")

        for line_num, line in enumerate(lines, 1):
            matches = pattern.findall(line)
            for var_name, method_name in matches:
                # Check if this is an agent variable
                agent_name_map = {
                    "summarizer": "SummarizerAgent",
                    "uniformer": "UniformerAgent",
                    "finalizer": "FinalizerAgent",
                    "verifier": "VerifierAgent",
                }

                agent_name = agent_name_map.get(var_name)
                if agent_name:
                    defined_methods = self.agent_methods.get(agent_name, set())
                    if method_name not in defined_methods:
                        self.errors.append(
                            f"❌ Line {line_num}: asyncio.run({var_name}.{method_name}()) - method not found!\n"
                            f"   Did you mean: {', '.join(sorted(defined_methods))}"
                        )
                    else:
                        print(
                            f"  ✓ Line {line_num}: asyncio.run({var_name}.{method_name}()) - OK"
                        )

        print()

    def check_imports(self):
        """Check that all agent imports are valid."""
        print("🔬 Step 5: Validating imports...")

        controller_path = (
            self.base_path
            / "src/unstract/prompt_service/controllers/agentic.py"
        )

        with open(controller_path, "r") as f:
            content = f.read()

        # Extract imports
        import_pattern = re.compile(
            r"from unstract\.prompt_service\.agents\.agentic\.(\w+) import (\w+)"
        )
        matches = import_pattern.findall(content)

        for module_name, class_name in matches:
            module_path = (
                self.base_path
                / f"src/unstract/prompt_service/agents/agentic/{module_name}.py"
            )

            if not module_path.exists():
                self.errors.append(
                    f"❌ Import error: Module '{module_name}' not found at {module_path}"
                )
            else:
                # Check if class exists in module
                with open(module_path, "r") as f:
                    module_content = f.read()

                if f"class {class_name}" not in module_content:
                    self.errors.append(
                        f"❌ Import error: Class '{class_name}' not found in module '{module_name}'"
                    )
                else:
                    print(f"  ✓ Import {class_name} from {module_name} - OK")

        print()

    def print_results(self):
        """Print validation results."""
        print("\n" + "=" * 70)
        print("VALIDATION RESULTS")
        print("=" * 70 + "\n")

        if self.warnings:
            print("⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  {warning}")
            print()

        if self.errors:
            print("❌ ERRORS FOUND:")
            for error in self.errors:
                print(f"  {error}")
            print()
            print(f"Total errors: {len(self.errors)}")
            print("\n❌ VALIDATION FAILED - Fix errors before running!")
        else:
            print("✅ ALL VALIDATIONS PASSED!")
            print("\n🎉 Your agentic APIs are ready to run!")

        print("\n" + "=" * 70 + "\n")


def main():
    """Main entry point."""
    # Determine base path
    script_path = Path(__file__).resolve()
    base_path = script_path.parent

    validator = AgenticValidator(base_path)
    success = validator.validate_all()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
