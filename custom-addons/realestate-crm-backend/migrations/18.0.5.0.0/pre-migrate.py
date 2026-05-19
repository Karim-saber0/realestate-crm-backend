# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Rename legacy columns and drop obsolete structured-line table."""
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'real_estate_installment_system'
          AND column_name = 'term_years'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            ALTER TABLE real_estate_installment_system
            RENAME COLUMN term_years TO duration_years
            """
        )
    cr.execute("DROP TABLE IF EXISTS real_estate_installment_system_line CASCADE")
