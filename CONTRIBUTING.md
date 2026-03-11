# Contributing to NSE F&O Scanner

First off, thank you for considering contributing to NSE F&O Scanner! It's people like you that make this project better for everyone.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How Can I Contribute?](#how-can-i-contribute)
- [Style Guidelines](#style-guidelines)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Community](#community)

## Code of Conduct

This project and everyone participating in it is governed by our commitment to fostering an open and welcoming environment. By participating, you are expected to uphold this code:

- Use welcoming and inclusive language
- Be respectful of differing viewpoints and experiences
- Gracefully accept constructive criticism
- Focus on what is best for the community
- Show empathy towards other community members

## Getting Started

### Prerequisites

- **Python 3.11+** (Backend)
- **Node.js 20+** (Frontend)
- **Git** for version control
- Basic understanding of FastAPI and React

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/fo-scanner.git
   cd fo-scanner
   ```
3. Add the upstream repository:
   ```bash
   git remote add upstream https://github.com/shahzebkhan-os/fo-scanner.git
   ```

## Development Setup

### Backend Setup

1. Create a virtual environment:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install development tools:
   ```bash
   pip install black isort pylint safety pytest
   ```

4. Copy environment variables:
   ```bash
   cp ../.env.example ../.env
   # Edit .env with your actual credentials
   ```

5. Initialize the database:
   ```bash
   python -c "import db; db.init_db()"
   ```

### Frontend Setup

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Install development tools (already in package.json):
   ```bash
   npm install --save-dev eslint prettier
   ```

### Running Locally

Use the provided startup script:
```bash
./start.sh
```

Or run separately:
```bash
# Terminal 1 - Backend
cd backend
python main.py

# Terminal 2 - Frontend
cd frontend
npm run dev
```

Access the application:
- Frontend: http://localhost:5175
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates.

When creating a bug report, include:
- **Clear title and description**
- **Steps to reproduce** the behavior
- **Expected behavior** vs actual behavior
- **Screenshots** if applicable
- **Environment details** (OS, Python/Node version)
- **Log files** or error messages

**Template:**
```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. See error

**Expected behavior**
What you expected to happen.

**Screenshots**
If applicable, add screenshots.

**Environment:**
 - OS: [e.g. Ubuntu 22.04]
 - Python Version: [e.g. 3.11.5]
 - Browser: [e.g. Chrome 120]
```

### Suggesting Features

Feature requests are welcome! Please provide:
- **Use case**: Why is this feature needed?
- **Proposed solution**: How should it work?
- **Alternatives considered**: What other approaches did you think about?
- **Additional context**: Screenshots, mockups, examples

### Code Contributions

#### Good First Issues

Look for issues labeled `good-first-issue` or `help-wanted`. These are great starting points!

#### Development Workflow

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

2. **Make your changes** following our style guidelines

3. **Test your changes**:
   ```bash
   # Backend tests
   cd backend
   python test_api.py

   # Frontend build
   cd frontend
   npm run build
   ```

4. **Format your code**:
   ```bash
   # Python
   black backend/
   isort backend/

   # JavaScript
   cd frontend
   npm run format
   ```

5. **Lint your code**:
   ```bash
   # Python
   pylint backend/*.py

   # JavaScript
   cd frontend
   npm run lint
   ```

6. **Commit your changes** (see commit guidelines below)

7. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

8. **Open a Pull Request** on GitHub

## Style Guidelines

### Python Code Style

We use **Black** for formatting and **pylint** for linting.

**Key points:**
- Line length: 120 characters
- Use type hints where appropriate
- Follow PEP 8 conventions
- Write docstrings for classes and complex functions
- Use meaningful variable names

**Example:**
```python
def calculate_greeks(
    spot_price: float,
    strike: float,
    days_to_expiry: int,
    volatility: float
) -> dict:
    """
    Calculate Black-Scholes Greeks for an option.

    Args:
        spot_price: Current price of underlying
        strike: Strike price of option
        days_to_expiry: Days until expiration
        volatility: Implied volatility (as decimal)

    Returns:
        Dictionary containing delta, gamma, theta, vega
    """
    # Implementation...
    return greeks_dict
```

### JavaScript Code Style

We use **Prettier** for formatting and **ESLint** for linting.

**Key points:**
- Use functional components with hooks
- Use arrow functions for callbacks
- Destructure props
- Use meaningful variable names
- Add PropTypes or TypeScript types

**Example:**
```javascript
const OptionChain = ({ symbol, strikes, onStrikeSelect }) => {
  const [selectedStrike, setSelectedStrike] = useState(null);

  const handleStrikeClick = (strike) => {
    setSelectedStrike(strike);
    onStrikeSelect?.(strike);
  };

  return (
    <div className="option-chain">
      {/* Component JSX */}
    </div>
  );
};
```

### File Organization

**Backend:**
```
backend/
├── main.py           # FastAPI app and routes
├── db.py             # Database operations
├── analytics.py      # Scoring and calculations
├── signals.py        # Signal generation
├── scheduler.py      # Background tasks
└── tests/            # Unit tests
```

**Frontend:**
```
frontend/
├── src/
│   ├── App.jsx       # Main application
│   ├── components/   # Reusable components
│   ├── hooks/        # Custom React hooks
│   └── utils/        # Helper functions
└── public/           # Static assets
```

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `build`: Build system or dependency changes
- `ci`: CI configuration changes
- `chore`: Other changes (maintenance tasks)

### Examples

```bash
feat(scanner): add IV Rank calculation to option scoring

Implements 52-week IV percentile ranking as described in #123.
The IVR is now factored into the option quality score.

Closes #123
```

```bash
fix(ui): correct PCR chart rendering on mobile

The PCR timeline chart was overflowing on small screens.
Added responsive breakpoints and adjusted container width.

Fixes #456
```

```bash
docs(readme): update installation instructions

- Add troubleshooting section
- Clarify Docker setup steps
- Fix broken links
```

### Commit Message Guidelines

- **Subject line**: Max 72 characters, imperative mood ("add" not "added")
- **Body**: Wrap at 72 characters, explain what and why (not how)
- **Footer**: Reference issues and PRs

## Pull Request Process

### Before Submitting

- [ ] Code follows project style guidelines
- [ ] All tests pass locally
- [ ] Code is properly formatted (black, prettier)
- [ ] New code has appropriate tests
- [ ] Documentation is updated
- [ ] Commit messages follow conventions
- [ ] Branch is up to date with main

### PR Template

When opening a PR, include:

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## How Has This Been Tested?
Describe how you tested your changes

## Screenshots (if applicable)
Add screenshots showing the changes

## Checklist
- [ ] My code follows the style guidelines
- [ ] I have performed a self-review
- [ ] I have commented my code where needed
- [ ] I have updated the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests
- [ ] All tests pass locally
```

### Review Process

1. **Automated checks** must pass (CI/CD pipeline)
2. At least **one maintainer approval** required
3. Address all review comments
4. Squash commits if requested
5. Maintainer will merge when ready

### After Merge

- Delete your feature branch
- Pull the latest changes from upstream
- Celebrate! 🎉

## Project Structure Decisions

### When to Add Dependencies

- Check if functionality can be achieved with existing dependencies
- Ensure the dependency is:
  - Actively maintained
  - Well-documented
  - Properly licensed
  - Reasonable size
- Discuss in an issue before adding large dependencies

### Database Changes

- Use database migrations (we plan to adopt Alembic)
- Never break existing data
- Provide rollback capability
- Document schema changes

### API Changes

- Maintain backwards compatibility when possible
- Version breaking changes (`/api/v2/...`)
- Update API documentation
- Add deprecation warnings before removal

## Testing

### Running Tests

```bash
# Backend tests
cd backend
python test_api.py

# Frontend tests (to be added)
cd frontend
npm test
```

### Writing Tests

- Write tests for new features
- Include edge cases
- Test error handling
- Keep tests simple and focused

**Example test:**
```python
def test_calculate_pcr():
    """Test PCR calculation with various scenarios."""
    # Normal case
    result = calculate_pcr(calls_oi=100000, puts_oi=150000)
    assert result == 1.5

    # Zero calls (edge case)
    result = calculate_pcr(calls_oi=0, puts_oi=100000)
    assert result == float('inf')
```

## Community

### Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For questions and general discussion
- **Documentation**: Check README and docs folder

### Recognition

Contributors are recognized in:
- README.md contributors section
- Release notes
- GitHub contributor graph

Thank you for contributing! 🚀

---

**Questions?** Open an issue or start a discussion. We're here to help!
