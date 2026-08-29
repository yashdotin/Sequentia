from django.core.management.base import BaseCommand, CommandError

from apps.catalog.services.catalog_validation import validate_catalog


class Command(BaseCommand):
    help = "Validate Sequentia canonical catalog data and relationships."

    def handle(self, *args, **options):
        result = validate_catalog()
        self.stdout.write(self.style.MIGRATE_HEADING("SEQUENTIA CATALOG VALIDATION"))
        for key, value in result.metrics.items():
            self.stdout.write(f"{key}: {value}")
        for warning in result.warnings:
            self.stdout.write(self.style.WARNING(f"WARNING: {warning}"))
        for error in result.errors:
            self.stdout.write(self.style.ERROR(f"ERROR: {error}"))
        if result.errors:
            raise CommandError(f"Catalog validation failed with {len(result.errors)} critical error(s).")
        self.stdout.write(self.style.SUCCESS("Catalog validation passed."))
