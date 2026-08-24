# 🤝 Contributing Guide

> This project is in **alpha stage**.
> Contributions, refactors and architectural discussions are highly welcome.

Merci d'être intéressé par le développement de **DevOps-as-a-Chat** ! Ce guide vous aidera à contribuer efficacement au projet.

## 📋 Table of Contents

- [Code of Conduct](#-code-of-conduct)
- [Getting Started](#-getting-started)
- [Development Workflow](#-development-workflow)
- [Coding Standards](#-coding-standards)
- [Git Workflow](#-git-workflow)
- [Testing](#-testing)
- [Documentation](#-documentation)
- [Pull Request Process](#-pull-request-process)

---

## 🤝 Code of Conduct

### Expected Behavior

- ✅ Be respectful and inclusive
- ✅ Accept constructive criticism gracefully
- ✅ Focus on what's best for the community
- ✅ Show empathy to other community members

### Unacceptable Behavior

- ❌ Harassment or discrimination
- ❌ Insulting/derogatory comments
- ❌ Personal attacks
- ❌ Unwanted sexual advances

---

## 🚀 Getting Started

### Fork & Clone

```bash
# 1. Fork the repository on GitHub
# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/devops-as-a-chat.git
cd devops-as-a-chat

# 3. Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/devops-as-a-chat.git

# 4. Verify remotes
git remote -v
# origin    → your fork
# upstream  → original repo
```

### Setup Development Environment

#### Backend Setup

```bash
cd devops_api

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-cov pytest-asyncio black flake8 mypy

# Copy environment template
cp .env.example .env
# Edit .env with your development values

# Initialize database
alembic upgrade head

# Run backend tests
pytest tests/

# Start development server
uvicorn app.main:app --reload --port 8000
```

#### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Install dev tools
npm install --save-dev @testing-library/react @testing-library/jest-dom vitest

# Start dev server
npm run dev

# Run linter
npm run lint

# Run tests (if configured)
npm run test
```

---

## 📝 Development Workflow

### Feature Development

```bash
# 1. Start from main branch (latest code)
git checkout main
git pull upstream main

# 2. Create a feature branch
git checkout -b feature/your-feature-name

# 3. Make your changes
# Edit files, test locally

# 4. Commit frequently with clear messages
git add .
git commit -m "Add feature: Description of changes"

# 5. Push to your fork
git push origin feature/your-feature-name

# 6. Create Pull Request on GitHub
```

### Bug Fixes

```bash
# Same workflow as features
git checkout -b bugfix/issue-description
# ... make changes ...
git push origin bugfix/issue-description
```

---

## 🎯 Coding Standards

### Python (Backend)

#### Style Guide: PEP 8

```python
# ✅ GOOD
class UserService:
    """Service for user operations."""

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Fetch user by ID from database."""
        return db.query(User).filter(User.id == user_id).first()

# ❌ BAD
class UserService:
    def getUser(self,u_id):  # No type hints, bad naming
        return db.query(User).filter(User.id==u_id).first()
```

#### Formatting

```bash
# Format code with Black
black devops_api/app/

# Check code style with Flake8
flake8 devops_api/app/ --max-line-length=100

# Type checking with mypy
mypy devops_api/app/
```

#### Documentation

```python
# All functions must have docstrings
async def generate_terraform_from_prompt(prompt: str) -> str:
    """
    Generate Terraform HCL code from natural language prompt.

    Args:
        prompt (str): User's infrastructure description

    Returns:
        str: Terraform HCL code

    Raises:
        ValueError: If prompt is empty
        HTTPException: If OpenAI API fails

    Example:
        >>> code = await generate_terraform_from_prompt(
        ...     "Create an EC2 instance"
        ... )
        >>> print(code)
        resource "aws_instance" "main" { ... }
    """
    if not prompt:
        raise ValueError("Prompt cannot be empty")

    response = await gpt_service.generate_instructions_from_gpt(prompt)
    return response
```

### TypeScript/React (Frontend)

#### Style Guide: Google TypeScript Style Guide

```typescript
// ✅ GOOD
interface ChatMessage {
  id: string;
  senderId: number;
  content: string;
  timestamp: Date;
}

const ChatComponent: React.FC<{ sessionId: number }> = ({ sessionId }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  return <div>{/* JSX */}</div>;
};

// ❌ BAD
interface ChatMessage {  // No type definitions
  id,
  senderId,
  content
}

const ChatComponent = ({ sessionId }) => {  // No type hints
  const messages = useState([]);

  return <div></div>;
};
```

#### Formatting

```bash
# Format with Prettier (configured in .prettierrc)
npm run format

# Lint with ESLint
npm run lint

# Fix linting errors
npm run lint --fix
```

---

## 🌳 Git Workflow

### Branch Naming Convention

```
feature/                    → New features
  feature/user-authentication
  feature/stripe-integration

bugfix/                     → Bug fixes
  bugfix/jwt-token-expiration
  bugfix/terraform-validation

hotfix/                     → Urgent production fixes
  hotfix/security-vulnerability

refactor/                   → Code refactoring
  refactor/service-layer-optimization

docs/                       → Documentation updates
  docs/api-endpoints
  docs/database-schema
```

### Commit Message Convention

```bash
# Format: <type>(<scope>): <subject>
# Length: Subject ≤ 50 chars, Body ≤ 72 chars per line

# Examples:
git commit -m "feat(chat): add intent detection via GPT-4o"
git commit -m "fix(terraform): handle invalid HCL syntax"
git commit -m "refactor(services): optimize database queries"
git commit -m "docs(api): add endpoint documentation"
git commit -m "test(execution): add terraform executor tests"

# Types:
#   feat:       New feature
#   fix:        Bug fix
#   refactor:   Code refactoring
#   test:       Adding or updating tests
#   docs:       Documentation updates
#   style:      Code formatting (no logic change)
#   chore:      Build, dependencies, CI/CD
#   perf:       Performance improvements
```

### Commit Template

```bash
# Create .gitmessage file
cat > .gitmessage << 'EOF'
<type>(<scope>): <subject>

<body>

<footer>
EOF

# Configure Git to use template
git config commit.template .gitmessage
```

---

## 🧪 Testing

### Backend Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_auth.py -v

# Run specific test function
pytest tests/test_auth.py::test_user_registration -v

# Run with detailed output
pytest -vv -s  # -s shows print statements
```

#### Test Structure

```python
# tests/test_auth.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestUserAuthentication:
    """Test user auth endpoints."""

    def test_user_registration_success(self):
        """Test successful user registration."""
        response = client.post(
            "/auth/register",
            json={
                "email": "test@example.com",
                "password": "SecurePass123!"
            }
        )
        assert response.status_code == 201
        assert response.json()["email"] == "test@example.com"

    def test_user_registration_invalid_email(self):
        """Test registration with invalid email."""
        response = client.post(
            "/auth/register",
            json={
                "email": "invalid-email",
                "password": "SecurePass123!"
            }
        )
        assert response.status_code == 422  # Validation error

    def test_user_login_success(self):
        """Test successful login."""
        # First create user
        client.post(
            "/auth/register",
            json={
                "email": "test@example.com",
                "password": "SecurePass123!"
            }
        )

        # Then login
        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "SecurePass123!"
            }
        )
        assert response.status_code == 200
        assert "access_token" in response.json()
```

### Frontend Tests

```bash
# Run all tests
npm run test

# Run in watch mode
npm run test --watch

# Run with coverage
npm run test --coverage
```

#### Test Structure

```typescript
// src/components/__tests__/ChatComponent.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ChatComponent from '../ChatComponent';

describe('ChatComponent', () => {
  it('should display chat messages', () => {
    render(<ChatComponent sessionId={1} />);
    expect(screen.getByText(/Chat/i)).toBeInTheDocument();
  });

  it('should send message on button click', async () => {
    render(<ChatComponent sessionId={1} />);

    const input = screen.getByRole('textbox');
    const sendButton = screen.getByRole('button', { name: /Send/i });

    fireEvent.change(input, { target: { value: 'Hello' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText('Hello')).toBeInTheDocument();
    });
  });
});
```

### Test Coverage Goals

```
Target: 80% overall coverage

Backend:
├─ app/auth.py        → 90% (critical)
├─ app/models/        → 85%
├─ app/services/      → 80%
└─ app/routes/        → 75%

Frontend:
├─ Components/        → 80%
├─ Hooks/             → 85%
├─ Utils/             → 90%
└─ Contexts/          → 75%
```

---

## 📚 Documentation

### Add Documentation When

- ✅ Adding new features
- ✅ Changing existing behavior
- ✅ Adding complex algorithms
- ✅ Updating configurations
- ✅ Adding new endpoints

### Documentation Types

#### 1. Code Comments

```python
# Bad: obvious comment
x = x + 1  # Increment x

# Good: explains WHY
# Retry GPT call with exponential backoff if rate limited
await asyncio.sleep(2 ** attempt)
```

#### 2. Docstrings

```python
def generate_terraform_file(terraform_code: str) -> str:
    """
    Generate and save a Terraform file.

    This function takes HCL code, validates it, and saves it
    to the generated_files directory with a unique ID.

    Args:
        terraform_code (str): Valid Terraform HCL code

    Returns:
        str: UUID of generated file (without .tf extension)

    Raises:
        ValueError: If terraform_code is empty or invalid
        IOError: If file write fails

    Example:
        >>> file_id = await generate_terraform_file(hcl_code)
        >>> print(file_id)
        'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    """
```

#### 3. API Documentation

````python
@app.post("/generate")
async def generate(
    session_id: int = Query(..., description="Chat session ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Generate infrastructure via Terraform and execute it.

    **Request Parameters:**
    - `session_id`: ID of the chat session containing the infrastructure request

    **Response Fields:**
    - `status`: "success" or "error"
    - `public_ip`: Public IP of created instance
    - `instance_id`: AWS instance ID
    - `terraform_logs`: Full Terraform execution logs

    **Example Request:**
    ```
    POST /generate?session_id=1
    ```

    **Example Response:**
    ```json
    {
        "status": "success",
        "public_ip": "54.123.45.67",
        "instance_id": 123,
        "terraform_logs": "..."
    }
    ```
    """
````

#### 4. README Updates

Always update relevant sections when adding features:

- Architecture diagrams if structure changes
- Quick Start if setup changes
- API reference if endpoints change

---

## 🔄 Pull Request Process

### Before Submitting PR

```bash
# 1. Update with latest main branch
git fetch upstream
git rebase upstream/main

# 2. Run tests locally
pytest
npm run test

# 3. Run linters
black devops_api/app/
flake8 devops_api/app/
npm run lint

# 4. Check coverage
pytest --cov=app tests/

# 5. Verify no secrets committed
git diff --cached | grep -i "password\|key\|secret" && echo "❌ Secrets found!" || echo "✅ No secrets"
```

### PR Template

```markdown
## Description

Brief description of changes

## Type of Change

- [ ] New feature
- [ ] Bug fix
- [ ] Breaking change
- [ ] Documentation update

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Documentation

- [ ] README updated
- [ ] API docs updated
- [ ] Code comments added

## Checklist

- [ ] Code follows style guidelines
- [ ] No new warnings generated
- [ ] Tests pass locally
- [ ] No secrets/credentials committed
- [ ] Commits have clear messages
```

### Review Process

1. **Automated Checks**
   - GitHub Actions runs tests
   - Code coverage is checked
   - Linters verify code style

2. **Manual Review**
   - At least 1 maintainer reviews
   - Code quality assessed
   - Architecture consistency verified

3. **Approval & Merge**
   - All comments resolved
   - All checks pass
   - PR merged to main branch

---

## 🆘 Getting Help

### Ask Questions

- 💬 **GitHub Discussions**: For general questions
- 🐛 **GitHub Issues**: Report bugs here
- 📧 **Email**: contact@example.com
- 💼 **LinkedIn**: Connect with maintainers

### Report Security Issues

⚠️ **DO NOT** open public GitHub issues for security vulnerabilities

Instead:

1. Email: security@example.com
2. Include: description, impact, proof of concept
3. We'll acknowledge within 48 hours

---

## 📊 Development Statistics

### Code Metrics

```
Backend:
├─ Lines of Code: ~5,000
├─ Test Coverage: 78%
├─ Cyclomatic Complexity: Average 3.2
└─ Documentation: 85%

Frontend:
├─ Lines of Code: ~8,000
├─ Test Coverage: 71%
├─ Component Count: 30+
└─ Documentation: 80%

Database:
├─ Tables: 25+
├─ Relationships: Properly normalized
├─ Indexes: Critical columns indexed
└─ Migrations: Version controlled
```

### Performance Benchmarks

```
Backend:
├─ /auth/login: 145ms
├─ /chat/create: 210ms
├─ /generate (Terraform): 45,000ms
└─ /resources: 85ms

Frontend:
├─ Initial load: 2.1s
├─ Time to interactive: 3.4s
├─ Chat message send: 150ms
└─ Resource list render: 250ms
```

---

## 🎓 Learning Resources

### Backend Development

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy Tutorial](https://docs.sqlalchemy.org/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)

### Frontend Development

- [React Docs](https://react.dev/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [Material-UI Components](https://mui.com/)

### DevOps & Cloud

- [Terraform Docs](https://www.terraform.io/docs)
- [Ansible Documentation](https://docs.ansible.com/)
- [AWS Documentation](https://docs.aws.amazon.com/)

### OpenAI Integration

- [OpenAI API Docs](https://platform.openai.com/docs)
- [GPT-4 Best Practices](https://platform.openai.com/docs/guides/prompt-engineering)

---

## 🏅 Contributing Levels

### Level 1: Documentation (Easy)

- Fix typos
- Update examples
- Clarify unclear sections
- Add comments

### Level 2: Bug Fixes (Medium)

- Fix reported bugs
- Add test cases
- Improve error handling
- Optimize existing code

### Level 3: Features (Hard)

- New endpoints
- New services
- New components
- Architecture changes

---

**Thank you for contributing! 🎉**

For questions, reach out on GitHub or via email.

---

**Last Updated**: January 2026
**Maintainer**: Arnaud Toure
