import ast
import openai
from professor_base import ProfessorBase

class ProfPatternSeeker(ProfessorBase):
    def __init__(self, session_id=None):
        # The system prompt is passed to the base class, which will store it.
        super().__init__(
            name="pattern_seeker",
            session_id=session_id,
            system_prompt=(
                "You are Prof. PatternSeeker, a cognitive systems theorist and software pattern classifier.\n"
                "You analyze code to uncover recurring architectural or logical motifs.\n\n"
                "Tasks:\n"
                "- Detect and name design patterns (e.g., observer, adapter, functional pipeline).\n"
                "- Identify anti-patterns or unoptimized constructs.\n"
                "- Suggest what paradigm the code leans toward (imperative, declarative, event-driven).\n"
                "- Return a fluent reflection on what patterns dominate the submitted code.\n\n"
                "Do not summarize. Reflect. Use engineering language but stay fluid and conceptual."
            )
        )
        self.model = "gpt-4o-mini" # You can still override the model here

    def _extract_ast_features(self, code: str) -> str:
        """Parses the code with AST to extract high-level structural features."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"[AST Parsing Failed]: {str(e)}"

        classes, functions, enums = [], [], []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                # Correctly handle base classes that might not be simple names
                base_names = [getattr(b, 'id', 'unknown_base') for b in node.bases]
                if "Enum" in base_names:
                    enums.append(class_name)
                else:
                    classes.append(class_name)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)

        summary = []
        if classes:
            summary.append(f"Detected classes: {', '.join(classes)}")
        if enums:
            summary.append(f"Detected enums: {', '.join(enums)}")
        if functions:
            summary.append(f"Detected functions: {', '.join(functions)}")

        return "\n".join(summary) if summary else "[No AST-level structures detected]"

    def run(self, code_blob: str) -> str:
        """
        Analyzes the code by creating a contextual prompt and then calling the base class's run method.
        """
        if not isinstance(code_blob, str) or not code_blob.strip():
            return "[ProfPatternSeeker] Error: Input must be a non-empty string of code."

        ast_summary = self._extract_ast_features(code_blob)

        # 1. Prepare the user-facing prompt with our specific context.
        user_prompt = (
            f"[AST Summary]\n{ast_summary}\n\n"
            f"[Code Input]\n{code_blob}"
        )

        # 2. Delegate the API call to the parent class's `run` method.
        #    This is the CORE FIX. The parent handles the system prompt and API logic.
        return super().run(user_prompt)

# Shortcut
process_with_pattern_seeker = lambda code_blob: ProfPatternSeeker().run(code_blob)

if __name__ == "__main__":
    seeker = ProfPatternSeeker()
    print("[ProfPatternSeeker] Paste Python code to analyze, then press Ctrl+D (Linux/macOS) or Ctrl+Z then Enter (Windows) to submit.")
    
    # Allow for multi-line input
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        pass
    
    code = "\n".join(lines)

    if code.strip():
        print("\n--- PATTERN REFLECTION ---\n")
        reflection = seeker.run(code)
        print(reflection)
    else:
        print("\nNo code provided.")