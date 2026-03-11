# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 4.x.x   | :white_check_mark: |
| < 4.0   | :x:                |

## Reporting a Vulnerability

We take the security of NSE F&O Scanner seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please Do Not:

- Open a public GitHub issue for security vulnerabilities
- Disclose the vulnerability publicly before it has been addressed
- Exploit the vulnerability beyond what is necessary to demonstrate it

### Reporting Process

**Please report security vulnerabilities by emailing:**

📧 **[Your Email Here]** or create a **private security advisory** on GitHub

Include the following information in your report:

1. **Type of vulnerability** (e.g., SQL injection, XSS, authentication bypass)
2. **Full paths of source file(s)** related to the vulnerability
3. **Location of the affected source code** (tag/branch/commit)
4. **Step-by-step instructions** to reproduce the issue
5. **Proof-of-concept or exploit code** (if possible)
6. **Impact of the vulnerability** and how it could be exploited
7. **Suggested fix** (if you have one)

### What to Expect

After you submit a report, here's what happens:

1. **Acknowledgment**: We'll acknowledge your email within **48 hours**
2. **Investigation**: We'll investigate and validate the vulnerability
3. **Updates**: We'll keep you informed about our progress
4. **Fix**: We'll work on a fix and coordinate disclosure timeline
5. **Credit**: With your permission, we'll credit you in our security advisory

**Expected Timeline:**
- Initial response: Within 48 hours
- Validation: Within 1 week
- Fix deployment: Within 2-4 weeks (depending on severity)
- Public disclosure: After fix is deployed

## Security Considerations for Users

### Environment Variables

⚠️ **Never commit your `.env` file to version control**

Your `.env` file contains sensitive credentials:
- `INDSTOCKS_TOKEN`: API access token
- `TELEGRAM_BOT_TOKEN`: Bot credentials
- `TELEGRAM_CHAT_ID`: Personal chat ID

**Best practices:**
- Keep `.env` in `.gitignore` (already configured)
- Use separate tokens for development and production
- Rotate tokens regularly
- Never share tokens in issues, pull requests, or screenshots

### API Security

When deploying to production:

1. **Enable authentication** on API endpoints
2. **Use HTTPS** for all external communication
3. **Implement rate limiting** to prevent abuse
4. **Validate all inputs** to prevent injection attacks
5. **Set appropriate CORS policies**

**Example CORS configuration:**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Restrict to your domain
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### Database Security

1. **Backup regularly**: SQLite database in `backend/scanner.db`
2. **Restrict file permissions**: `chmod 600 backend/scanner.db`
3. **Consider encryption at rest** for production
4. **Never expose database file** via web server

### Dependencies

We regularly scan dependencies for vulnerabilities:
- Python: `safety check`
- JavaScript: `npm audit`
- GitHub: Dependabot alerts

**To check for vulnerabilities:**
```bash
# Python dependencies
cd backend
safety check --file requirements.txt

# JavaScript dependencies
cd frontend
npm audit

# Fix npm vulnerabilities
npm audit fix
```

### Docker Security

When using Docker in production:

1. **Don't run as root**: Use non-root user in Dockerfile
2. **Scan images**: Use `docker scan` or Trivy
3. **Update base images**: Keep `python:3.11-slim` up to date
4. **Limit resources**: Set memory and CPU limits
5. **Use secrets management**: Don't bake secrets into images

**Example resource limits:**
```yaml
services:
  fo-scanner:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

## Known Security Limitations

### Current Limitations

1. **No built-in authentication**: API endpoints are currently unauthenticated
2. **No rate limiting**: Could be susceptible to DoS attacks
3. **SQLite database**: Not suitable for high-concurrency production use
4. **No encryption**: Data stored in plain text in database
5. **Single-user design**: Not designed for multi-tenant deployment

### Recommendations for Production

If deploying this application in production:

- [ ] Add authentication middleware (JWT, OAuth2, API keys)
- [ ] Implement rate limiting (slowapi, nginx)
- [ ] Consider PostgreSQL instead of SQLite
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Set up monitoring and alerting
- [ ] Implement audit logging
- [ ] Use a secrets manager (AWS Secrets Manager, HashiCorp Vault)
- [ ] Regular security audits and penetration testing

## Security Best Practices for Contributors

When contributing code:

1. **Never commit secrets**: Check files before committing
2. **Validate user inputs**: Use Pydantic models for validation
3. **Sanitize outputs**: Prevent XSS in frontend
4. **Use parameterized queries**: Already using SQLite safely
5. **Handle errors gracefully**: Don't expose stack traces to users
6. **Keep dependencies updated**: Regularly update packages
7. **Review security implications**: Consider security in code reviews

### Code Review Checklist

- [ ] No hardcoded credentials
- [ ] Input validation on all user-supplied data
- [ ] SQL queries use parameterized statements
- [ ] File operations validate paths (prevent directory traversal)
- [ ] Error messages don't leak sensitive information
- [ ] Authentication/authorization checks where needed
- [ ] Rate limiting on expensive operations
- [ ] Logging doesn't include sensitive data

## Responsible Disclosure

We believe in responsible disclosure and will:

- Work with you to understand and validate the vulnerability
- Keep you informed throughout the process
- Acknowledge your contribution (with your permission)
- Coordinate disclosure timing to protect users

We expect security researchers to:

- Give us reasonable time to fix the issue before public disclosure
- Make a good faith effort to avoid privacy violations
- Not access or modify other users' data
- Not perform DoS attacks or social engineering

## Security Updates

Security updates will be:

1. **Announced** in GitHub Security Advisories
2. **Tagged** with appropriate severity level
3. **Documented** in release notes
4. **Deployed** via patch releases

Subscribe to **GitHub notifications** to stay informed.

## Recognition

We believe in recognizing security researchers who help improve our security:

- **Hall of Fame**: Listed in SECURITY.md (if you agree)
- **Credit in advisories**: Named in security advisories
- **Special thanks**: Mentioned in release notes

### Security Researchers Hall of Fame

<!-- Will be added as researchers report vulnerabilities -->
*No vulnerabilities reported yet. Be the first!*

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [React Security Best Practices](https://react.dev/learn/security)
- [Docker Security Best Practices](https://docs.docker.com/develop/security-best-practices/)

## Questions?

If you have questions about security that don't involve reporting a vulnerability:

- Open a **GitHub Discussion**
- Check existing **GitHub Issues**
- Review our **CONTRIBUTING.md**

---

**Last Updated:** March 11, 2026

Thank you for helping keep NSE F&O Scanner secure! 🔒
