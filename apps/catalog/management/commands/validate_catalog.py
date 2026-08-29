from django.core.management.base import BaseCommand, CommandError

from apps.catalog.services.catalog_validation import run_validation


class Command(BaseCommand):
    help = (
        "Validates the skill vocabulary, course metadata, and project seed together: "
        "dangling references, orphan skills, duplicate slugs, invalid roles, and "
        "coverage gaps. Exits non-zero on any data-integrity error."
    )

    def handle(self, *args, **options):
        try:
            report = run_validation()
        except Exception as exc:
            raise CommandError(f"Catalog failed to load: {exc}") from exc

        self.stdout.write("Catalog summary:")
        self.stdout.write(f"  Skills:  {report.skill_count}")
        self.stdout.write(f"  Courses: {report.course_count}")
        self.stdout.write(f"  Projects: {report.project_count}")
        self.stdout.write(f"  Roles:   {report.role_count}")
        self.stdout.write(f"  Domains: {report.domain_count}")
        self.stdout.write(
            f"  Projects with a genuinely distinct prerequisite set: "
            f"{report.projects_with_distinct_prerequisites}/{report.project_count}"
        )
        if report.courses_without_review_data:
            self.stdout.write(
                f"  Courses without review data (excluded from semantic scoring): "
                f"{len(report.courses_without_review_data)}"
            )

        if report.warnings:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"{len(report.warnings)} warning(s):"))
            for w in report.warnings:
                self.stdout.write(self.style.WARNING(f"  - {w}"))
            if report.thin_roles:
                self.stdout.write("  Projects per role (below target of 10):")
                for role, count in sorted(report.thin_roles.items(), key=lambda kv: kv[1]):
                    self.stdout.write(f"    {role}: {count}")
            if report.thin_domains:
                self.stdout.write("  Courses per domain (below target of 3):")
                for domain, count in sorted(report.thin_domains.items(), key=lambda kv: kv[1]):
                    self.stdout.write(f"    {domain}: {count}")

        if report.errors:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"{len(report.errors)} error(s):"))
            for e in report.errors:
                self.stdout.write(self.style.ERROR(f"  - {e}"))
            raise CommandError(f"Catalog validation failed with {len(report.errors)} error(s).")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Catalog validation passed."))
