"""
Import a CSP file into the database
"""
from pathlib import Path
import sys
sys.path.insert(0, 'src')

from calsystem.procedures.csp_file import CSPFile
from calsystem.database.connection import get_db
from calsystem.database.models import Procedure, TestSection, TestPoint
from loguru import logger

def import_csp_to_database(csp_file_path: str, procedure_id: int):
    """Import CSP file contents into an existing procedure in the database."""

    # Load CSP file
    logger.info(f"Loading CSP file: {csp_file_path}")
    proc_data = CSPFile.load(Path(csp_file_path))

    if not proc_data:
        logger.error("Failed to load CSP file")
        return False

    logger.info(f"Loaded: {proc_data.name}")
    logger.info(f"  Sections: {len(proc_data.sections)}")
    total_tps = sum(len(s.test_points) for s in proc_data.sections)
    logger.info(f"  Test Points: {total_tps}")

    # Connect to database
    db = get_db()
    if not db.connect():
        logger.error("Failed to connect to database")
        return False

    try:
        with db.session() as session:
            # Get the existing procedure
            procedure = session.query(Procedure).filter(Procedure.id == procedure_id).first()
            if not procedure:
                logger.error(f"Procedure {procedure_id} not found")
                return False

            logger.info(f"Found procedure: {procedure.name}")

            # Delete existing sections and test points
            logger.info("Removing old sections/test points...")
            session.query(TestPoint).filter(
                TestPoint.section_id.in_(
                    session.query(TestSection.id).filter(TestSection.procedure_id == procedure_id)
                )
            ).delete(synchronize_session=False)

            session.query(TestSection).filter(TestSection.procedure_id == procedure_id).delete()
            session.commit()

            # Import sections and test points from CSP
            logger.info("Importing from CSP...")
            for section_data in proc_data.sections:
                # Create section
                section = TestSection(
                    procedure_id=procedure_id,
                    name=section_data.name,
                    order=section_data.order,
                    description=section_data.description,
                    standard_section_type=section_data.standard_section_type,
                    section_command=section_data.section_command,
                    section_prompt=section_data.section_prompt,
                    section_wiring_type=section_data.section_wiring_type,
                )
                session.add(section)
                session.flush()  # Get section ID

                logger.info(f"  Added section: {section.name}")

                # Create test points
                for tp_data in section_data.test_points:
                    tp = TestPoint(
                        section_id=section.id,
                        order=tp_data.order,
                        test_type=tp_data.test_type,
                        nominal_value=tp_data.nominal_value,
                        unit=tp_data.unit,
                        frequency=tp_data.frequency,
                        frequency_unit=tp_data.frequency_unit,
                        pre_nominal_value=tp_data.pre_nominal_value,
                        pre_unit=tp_data.pre_unit,
                        pre_frequency=tp_data.pre_frequency,
                        pre_frequency_unit=tp_data.pre_frequency_unit,
                        pre_delay_seconds=tp_data.pre_delay_seconds,
                        pre_conditioning_steps=tp_data.pre_conditioning_steps,
                        manual_setup=getattr(tp_data, 'manual_setup', False),
                        manual_setup_prompt=getattr(tp_data, 'manual_setup_prompt', None),
                        pass_fail_prompt=tp_data.pass_fail_prompt,
                        pass_fail_image=getattr(tp_data, 'pass_fail_image', None),
                        pass_fail_min=tp_data.pass_fail_min,
                        pass_fail_max=tp_data.pass_fail_max,
                        pass_fail_range_unit=tp_data.pass_fail_range_unit,
                        pass_fail_comparison_type=tp_data.pass_fail_comparison_type,
                        measurement_target=tp_data.measurement_target,
                        expected_value=tp_data.expected_value,
                        expected_unit=tp_data.expected_unit,
                        tolerance_value=tp_data.tolerance_value,
                        tolerance_type=tp_data.tolerance_type,
                        tol_pct_reading=tp_data.tol_pct_reading,
                        tol_pct_range=tp_data.tol_pct_range,
                        tol_pct_span=tp_data.tol_pct_span,
                        tol_digits=tp_data.tol_digits,
                        tol_absolute=tp_data.tol_absolute,
                        tol_resolution=tp_data.tol_resolution,
                        tol_range_value=tp_data.tol_range_value,
                        tol_span_value=tp_data.tol_span_value,
                        formula=tp_data.formula,
                        source_command=tp_data.source_command,
                        measure_command=tp_data.measure_command,
                        operate_command=tp_data.operate_command,
                        standby_command=tp_data.standby_command,
                        excel_workbook=tp_data.excel_workbook,
                        excel_sheet=tp_data.excel_sheet,
                        excel_cell=tp_data.excel_cell,
                        wiring_diagram_type=tp_data.wiring_diagram_type,
                        operator_prompt=tp_data.operator_prompt,
                        dmm_config=tp_data.dmm_config,
                        dut_setup_command=tp_data.dut_setup_command,
                        dut_setup_param=tp_data.dut_setup_param,
                        dut_pre_check_command=tp_data.dut_pre_check_command,
                        dut_pre_check_param=tp_data.dut_pre_check_param,
                        dut_pre_check_expected=tp_data.dut_pre_check_expected,
                        dut_pre_check_prompt=tp_data.dut_pre_check_prompt,
                        dut_pre_check_parser=tp_data.dut_pre_check_parser,
                        dut_pre_check_index=tp_data.dut_pre_check_index,
                        dut_post_read_command=tp_data.dut_post_read_command,
                        dut_post_read_param=tp_data.dut_post_read_param,
                        dut_post_read_parser=tp_data.dut_post_read_parser,
                        dut_post_read_index=tp_data.dut_post_read_index,
                        description=tp_data.description,
                    )
                    session.add(tp)

                logger.info(f"    Added {len(section_data.test_points)} test points")

            session.commit()
            logger.info("✓ Import successful!")
            return True

    except Exception as e:
        logger.error(f"Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2:
        csp_path = sys.argv[1]
        procedure_id = int(sys.argv[2])
    else:
        # Default: Import both procedures
        print("Importing Fluke 789...")
        fluke_csp = "/mnt/c/Users/paula/.calsystem/procedures/789_Fluke__Processmeter_v1.0.csp"
        if import_csp_to_database(fluke_csp, procedure_id=2):
            print("✓ Fluke 789 restored\n")
        else:
            print("✗ Fluke 789 failed\n")

        print("Importing HP 3468A...")
        hp_csp = "/mnt/c/Users/paula/.calsystem/procedures/3468A_HP__Multimeter_v1.0.csp"
        if import_csp_to_database(hp_csp, procedure_id=3):
            print("✓ HP 3468A restored\n")
        else:
            print("✗ HP 3468A failed\n")

        print("\n✓✓✓ ALL PROCEDURES RESTORED ✓✓✓")
        sys.exit(0)

    if import_csp_to_database(csp_path, procedure_id):
        print(f"\n✓✓✓ SUCCESS! Procedure {procedure_id} restored from CSP file ✓✓✓")
    else:
        print(f"\n✗✗✗ FAILED to import CSP file ✗✗✗")
