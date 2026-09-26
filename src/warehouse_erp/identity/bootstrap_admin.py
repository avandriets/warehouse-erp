import argparse

from warehouse_erp.database import SessionFactory
from warehouse_erp.identity.application.service import IdentityService
from warehouse_erp.identity.infrastructure.repositories import SqlAlchemyIdentityUnitOfWork


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or activate the first ERP administrator")
    parser.add_argument(
        "--auth0-sub",
        required=True,
        help="Auth0 user subject, for example auth0|...",
    )
    parser.add_argument("--email")
    parser.add_argument("--display-name")
    arguments = parser.parse_args()

    with SessionFactory() as session:
        service = IdentityService(SqlAlchemyIdentityUnitOfWork(session))
        user = service.bootstrap_admin(
            auth0_subject=arguments.auth0_sub,
            email=arguments.email,
            display_name=arguments.display_name,
        )

    print(f"Administrator ready: {user.id} ({user.auth0_subject})")


if __name__ == "__main__":
    main()
