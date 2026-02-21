import os
import click
from dotenv import load_dotenv

load_dotenv()

from app import create_app, db

app = create_app()


@app.cli.command('create-admin')
@click.option('--username', prompt=True)
@click.option('--email', prompt=True)
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
def create_admin(username, email, password):
    """Create an admin user."""
    from app.models.user import User
    if User.query.filter_by(username=username).first():
        click.echo(f'User {username} already exists.')
        return
    user = User(username=username, email=email, role='admin')
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo(f'Admin user {username} created.')


@app.cli.command('seed-bas')
@click.option('--company-id', type=int, prompt=True)
def seed_bas(company_id):
    """Seed BAS kontoplan for a company."""
    from app.models.company import Company
    company = db.session.get(Company, company_id)
    if not company:
        click.echo(f'Company {company_id} not found.')
        return
    from app.utils.bas_kontoplan import seed_accounts_for_company
    count = seed_accounts_for_company(company_id)
    click.echo(f'Seeded {count} accounts for {company.name}.')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004)
