"""
Industry-standard benchmarks for die-casting manufacturing processes.
Defines scrap rates, downtime percentages, OEE targets, and performance grading criteria.
Sourced from industry research, manufacturing best practices, and benchmarking studies.
"""

# Industry Standard Manufacturing Benchmarks
DIE_CASTING_STANDARDS = {
    "scrap_rates": {
        "cold_shot": 0.15,  # 15% - incomplete filling
        "porosity": 0.08,  # 8% - air entrapment
        "dimensional": 0.05,  # 5% - size issues
        "surface_defects": 0.03,  # 3% - cosmetic issues
        "total_typical": 0.25,  # 25% total typical scrap rate
        "world_class": 0.15,  # 15% world-class scrap rate
    },
    "downtime": {
        "planned_maintenance": 0.05,  # 5% - scheduled maintenance
        "unplanned_maintenance": 0.08,  # 8% - breakdowns
        "setup_changeover": 0.12,  # 12% - die changes
        "material_issues": 0.03,  # 3% - material problems
        "total_typical": 0.28,  # 28% total typical downtime
        "world_class": 0.15,  # 15% world-class downtime
    },
    "efficiency": {
        "typical": 0.75,  # 75% typical efficiency
        "good": 0.85,  # 85% good efficiency
        "world_class": 0.92,  # 92% world-class efficiency
    },
    "cycle_time": {
        "variance_threshold": 0.15,  # 15% acceptable variance
        "optimization_target": 0.10,  # 10% optimization target
    },
}

INJECTION_MOLDING_STANDARDS = {
    "scrap_rates": {
        "short_shot": 0.12,  # 12% - incomplete filling
        "flash": 0.06,  # 6% - excess material
        "sink_marks": 0.04,  # 4% - surface defects
        "dimensional": 0.03,  # 3% - size issues
        "total_typical": 0.20,  # 20% total typical scrap rate
        "world_class": 0.12,  # 12% world-class scrap rate
    },
    "downtime": {
        "planned_maintenance": 0.04,  # 4% - scheduled maintenance
        "unplanned_maintenance": 0.06,  # 6% - breakdowns
        "setup_changeover": 0.08,  # 8% - mold changes
        "material_issues": 0.02,  # 2% - material problems
        "total_typical": 0.20,  # 20% total typical downtime
        "world_class": 0.12,  # 12% world-class downtime
    },
    "efficiency": {
        "typical": 0.80,  # 80% typical efficiency
        "good": 0.88,  # 88% good efficiency
        "world_class": 0.94,  # 94% world-class efficiency
    },
    "cycle_time": {
        "variance_threshold": 0.12,  # 12% acceptable variance
        "optimization_target": 0.08,  # 8% optimization target
    },
}

STAMPING_STANDARDS = {
    "scrap_rates": {
        "material_waste": 0.10,  # 10% - material waste
        "dimensional": 0.05,  # 5% - size issues
        "surface_defects": 0.03,  # 3% - surface issues
        "total_typical": 0.18,  # 18% total typical scrap rate
        "world_class": 0.10,  # 10% world-class scrap rate
    },
    "downtime": {
        "planned_maintenance": 0.03,  # 3% - scheduled maintenance
        "unplanned_maintenance": 0.05,  # 5% - breakdowns
        "setup_changeover": 0.06,  # 6% - die changes
        "material_issues": 0.02,  # 2% - material problems
        "total_typical": 0.16,  # 16% total typical downtime
        "world_class": 0.10,  # 10% world-class downtime
    },
    "efficiency": {
        "typical": 0.82,  # 82% typical efficiency
        "good": 0.90,  # 90% good efficiency
        "world_class": 0.95,  # 95% world-class efficiency
    },
    "cycle_time": {
        "variance_threshold": 0.10,  # 10% acceptable variance
        "optimization_target": 0.06,  # 6% optimization target
    },
}

COMPRESSION_STANDARDS = {
    "scrap_rates": {
        "cure_issues": 0.08,  # 8% - curing problems
        "dimensional": 0.04,  # 4% - size issues
        "surface_defects": 0.03,  # 3% - surface issues
        "total_typical": 0.15,  # 15% total typical scrap rate
        "world_class": 0.08,  # 8% world-class scrap rate
    },
    "downtime": {
        "planned_maintenance": 0.04,  # 4% - scheduled maintenance
        "unplanned_maintenance": 0.05,  # 5% - breakdowns
        "setup_changeover": 0.05,  # 5% - mold changes
        "material_issues": 0.02,  # 2% - material problems
        "total_typical": 0.16,  # 16% total typical downtime
        "world_class": 0.10,  # 10% world-class downtime
    },
    "efficiency": {
        "typical": 0.78,  # 78% typical efficiency
        "good": 0.86,  # 86% good efficiency
        "world_class": 0.92,  # 92% world-class efficiency
    },
    "cycle_time": {
        "variance_threshold": 0.18,  # 18% acceptable variance
        "optimization_target": 0.12,  # 12% optimization target
    },
}

ASSEMBLY_STANDARDS = {
    "scrap_rates": {
        "assembly_errors": 0.05,  # 5% - assembly mistakes
        "quality_issues": 0.03,  # 3% - quality problems
        "total_typical": 0.08,  # 8% total typical scrap rate
        "world_class": 0.05,  # 5% world-class scrap rate
    },
    "downtime": {
        "planned_maintenance": 0.02,  # 2% - scheduled maintenance
        "unplanned_maintenance": 0.03,  # 3% - breakdowns
        "setup_changeover": 0.04,  # 4% - line changes
        "material_issues": 0.01,  # 1% - material problems
        "total_typical": 0.10,  # 10% total typical downtime
        "world_class": 0.06,  # 6% world-class downtime
    },
    "efficiency": {
        "typical": 0.85,  # 85% typical efficiency
        "good": 0.92,  # 92% good efficiency
        "world_class": 0.96,  # 96% world-class efficiency
    },
    "cycle_time": {
        "variance_threshold": 0.08,  # 8% acceptable variance
        "optimization_target": 0.05,  # 5% optimization target
    },
}

# Process mapping
PROCESS_STANDARDS = {
    "Die Casting": DIE_CASTING_STANDARDS,
    "Injection Molding": INJECTION_MOLDING_STANDARDS,
    "Stamping": STAMPING_STANDARDS,
    "Compression": COMPRESSION_STANDARDS,
    "Assembly": ASSEMBLY_STANDARDS,
}


class IndustryStandardsAnalyzer:
    """
    Analyzer for comparing manufacturing performance against industry standards
    """

    def __init__(self, tooling_family="Injection Molding"):
        """
        Initialize the analyzer with specific tooling family standards

        Args:
            tooling_family (str): The manufacturing process type
        """
        self.tooling_family = tooling_family
        self.standards = PROCESS_STANDARDS.get(
            tooling_family, INJECTION_MOLDING_STANDARDS
        )

    def calculate_scrap_metrics(self, df):
        """
        Calculate scrap metrics and compare to industry standards

        Args:
            df (pd.DataFrame): Manufacturing data

        Returns:
            dict: Scrap metrics with industry comparison
        """
        try:
            # Calculate actual scrap rate using real scrap data
            if "SCRAP_INDICATOR" in df.columns:
                # Use comprehensive scrap indicator from Pareto analysis
                total_shots = len(df)
                total_scrap = df["SCRAP_INDICATOR"].sum()
                actual_scrap_rate = (
                    (total_scrap / total_shots) * 100 if total_shots > 0 else 0
                )
            elif "SCRAP_FLAG" in df.columns:
                # Use basic scrap flag from Pareto analysis
                total_shots = len(df)
                total_scrap = df["SCRAP_FLAG"].sum()
                actual_scrap_rate = (
                    (total_scrap / total_shots) * 100 if total_shots > 0 else 0
                )
            elif "SCRAP" in df.columns:
                # Use actual scrap column if available
                total_shots = len(df)
                total_scrap = df["SCRAP"].sum()
                actual_scrap_rate = (
                    (total_scrap / total_shots) * 100 if total_shots > 0 else 0
                )
            else:
                # Fallback to estimation from CT issues if no scrap data
                if "CT_ISSUE_FLAG" in df.columns:
                    ct_issues = df["CT_ISSUE_FLAG"].sum()
                    total_shots = len(df)
                    # Assume 10% of CT issues result in scrap
                    estimated_scrap = int(ct_issues * 0.1)
                    actual_scrap_rate = (
                        (estimated_scrap / total_shots) * 100 if total_shots > 0 else 0
                    )
                else:
                    actual_scrap_rate = 0

            # Get industry benchmarks
            industry_benchmark = self.standards["scrap_rates"]["total_typical"] * 100
            world_class_target = self.standards["scrap_rates"]["world_class"] * 100

            # Determine performance grade
            if actual_scrap_rate <= world_class_target:
                performance_grade = "World-Class"
            elif actual_scrap_rate <= industry_benchmark:
                performance_grade = "Good"
            elif actual_scrap_rate <= industry_benchmark * 1.5:
                performance_grade = "Typical"
            else:
                performance_grade = "Poor"

            # Calculate improvement potential
            improvement_potential = max(0, actual_scrap_rate - world_class_target)

            return {
                "scrap_rate": actual_scrap_rate,
                "industry_benchmark": industry_benchmark,
                "world_class_target": world_class_target,
                "performance_grade": performance_grade,
                "improvement_potential": improvement_potential,
            }

        except Exception as e:
            print(f"⚠️ Error calculating scrap metrics: {str(e)}")
            return {
                "scrap_rate": 0,
                "industry_benchmark": 0,
                "world_class_target": 0,
                "performance_grade": "N/A",
                "improvement_potential": 0,
            }

    def calculate_downtime_metrics(self, df):
        """
        Calculate downtime metrics and compare to industry standards

        Args:
            df (pd.DataFrame): Manufacturing data

        Returns:
            dict: Downtime metrics with industry comparison
        """
        try:
            # Calculate actual downtime rate using real downtime data
            if "DOWNTIME" in df.columns:
                # Use real downtime calculation from company logic
                total_downtime = df["DOWNTIME"].sum()
                total_time = len(df) * 60  # Assume 1 minute per shot
                actual_downtime_rate = (
                    (total_downtime / total_time) * 100 if total_time > 0 else 0
                )
            else:
                # Fallback to estimation from CT issues if no downtime data
                if "CT_ISSUE_FLAG" in df.columns:
                    ct_issues = df["CT_ISSUE_FLAG"].sum()
                    total_shots = len(df)
                    # Assume 5 minutes per CT issue
                    estimated_downtime = ct_issues * 5
                    total_time = total_shots * 60  # Assume 1 minute per shot
                    actual_downtime_rate = (
                        (estimated_downtime / total_time) * 100 if total_time > 0 else 0
                    )
                else:
                    actual_downtime_rate = 0

            # Get industry benchmarks
            industry_benchmark = self.standards["downtime"]["total_typical"] * 100
            world_class_target = self.standards["downtime"]["world_class"] * 100

            # Determine performance grade
            if actual_downtime_rate <= world_class_target:
                performance_grade = "World-Class"
            elif actual_downtime_rate <= industry_benchmark:
                performance_grade = "Good"
            elif actual_downtime_rate <= industry_benchmark * 1.5:
                performance_grade = "Typical"
            else:
                performance_grade = "Poor"

            # Calculate improvement potential
            improvement_potential = max(0, actual_downtime_rate - world_class_target)

            return {
                "actual_downtime_rate": actual_downtime_rate,
                "industry_benchmark": industry_benchmark,
                "world_class_target": world_class_target,
                "performance_grade": performance_grade,
                "improvement_potential": improvement_potential,
            }

        except Exception as e:
            print(f"⚠️ Error calculating downtime metrics: {str(e)}")
            return {
                "actual_downtime_rate": 0,
                "industry_benchmark": 0,
                "world_class_target": 0,
                "performance_grade": "N/A",
                "improvement_potential": 0,
            }

    def calculate_efficiency_metrics(self, df):
        """
        Calculate efficiency metrics and compare to industry standards

        Args:
            df (pd.DataFrame): Manufacturing data

        Returns:
            dict: Efficiency metrics with industry comparison
        """
        try:
            # Calculate actual efficiency
            if "EFFICIENCY" in df.columns:
                average_efficiency = df["EFFICIENCY"].mean()
            else:
                # Calculate from CT and APPROVED_CT if available
                if "CT" in df.columns and "APPROVED_CT" in df.columns:
                    efficiency = (df["APPROVED_CT"] / df["CT"]) * 100
                    efficiency = efficiency.clip(upper=100)  # Cap at 100%
                    average_efficiency = efficiency.mean()
                else:
                    average_efficiency = 0

            # Get industry benchmarks
            industry_benchmark = self.standards["efficiency"]["typical"] * 100
            world_class_target = self.standards["efficiency"]["world_class"] * 100

            # Determine performance grade
            if average_efficiency >= world_class_target:
                performance_grade = "World-Class"
            elif average_efficiency >= industry_benchmark:
                performance_grade = "Good"
            elif average_efficiency >= industry_benchmark * 0.9:
                performance_grade = "Typical"
            else:
                performance_grade = "Poor"

            # Calculate improvement potential
            improvement_potential = max(0, world_class_target - average_efficiency)

            return {
                "average_efficiency": average_efficiency,
                "industry_benchmark": industry_benchmark,
                "world_class_target": world_class_target,
                "performance_grade": performance_grade,
                "improvement_potential": improvement_potential,
            }

        except Exception as e:
            print(f"⚠️ Error calculating efficiency metrics: {str(e)}")
            return {
                "average_efficiency": 0,
                "industry_benchmark": 0,
                "world_class_target": 0,
                "performance_grade": "N/A",
                "improvement_potential": 0,
            }

    def generate_process_specific_recommendations(
        self, scrap_metrics, downtime_metrics, efficiency_metrics
    ):
        """
        Generate process-specific recommendations based on performance vs industry standards

        Args:
            scrap_metrics (dict): Scrap performance metrics
            downtime_metrics (dict): Downtime performance metrics
            efficiency_metrics (dict): Efficiency performance metrics

        Returns:
            dict: Process-specific recommendations
        """
        recommendations = {"process_specific": [], "high_priority": []}

        # Scrap recommendations
        if scrap_metrics.get("performance_grade") == "Poor":
            if self.tooling_family == "Die Casting":
                recommendations["high_priority"].extend(
                    [
                        "Optimize die temperature and pressure settings",
                        "Implement real-time porosity detection",
                        "Improve die lubrication and maintenance",
                    ]
                )
            elif self.tooling_family == "Injection Molding":
                recommendations["high_priority"].extend(
                    [
                        "Optimize injection pressure and speed",
                        "Implement mold temperature control",
                        "Improve material drying and handling",
                    ]
                )

        # Downtime recommendations
        if downtime_metrics.get("performance_grade") == "Poor":
            recommendations["high_priority"].extend(
                [
                    "Implement predictive maintenance program",
                    "Optimize changeover procedures",
                    "Improve spare parts management",
                ]
            )

        # Efficiency recommendations
        if efficiency_metrics.get("performance_grade") == "Poor":
            recommendations["high_priority"].extend(
                [
                    "Optimize cycle time parameters",
                    "Implement operator training programs",
                    "Improve process monitoring and control",
                ]
            )

        # Process-specific recommendations
        if self.tooling_family == "Die Casting":
            recommendations["process_specific"].extend(
                [
                    "Implement die temperature monitoring",
                    "Optimize shot size and pressure",
                    "Improve die cooling system efficiency",
                ]
            )
        elif self.tooling_family == "Injection Molding":
            recommendations["process_specific"].extend(
                [
                    "Implement mold temperature control",
                    "Optimize injection and cooling times",
                    "Improve material flow analysis",
                ]
            )

        return recommendations


def get_industry_comparison_chart_data(df, tooling_family):
    """
    Generate chart data for industry comparison visualization

    Args:
        df (pd.DataFrame): Manufacturing data
        tooling_family (str): Manufacturing process type

    Returns:
        dict: Chart data for visualization
    """
    try:
        analyzer = IndustryStandardsAnalyzer(tooling_family)

        # Calculate metrics
        scrap_metrics = analyzer.calculate_scrap_metrics(df)
        downtime_metrics = analyzer.calculate_downtime_metrics(df)
        efficiency_metrics = analyzer.calculate_efficiency_metrics(df)

        # Prepare chart data
        chart_data = {
            "scrap": {
                "actual": scrap_metrics.get("scrap_rate", 0),
                "industry": scrap_metrics.get("industry_benchmark", 0),
                "world_class": scrap_metrics.get("world_class_target", 0),
            },
            "downtime": {
                "actual": downtime_metrics.get("actual_downtime_rate", 0),
                "industry": downtime_metrics.get("industry_benchmark", 0),
                "world_class": downtime_metrics.get("world_class_target", 0),
            },
            "efficiency": {
                "actual": efficiency_metrics.get("average_efficiency", 0),
                "industry": efficiency_metrics.get("industry_benchmark", 0),
                "world_class": efficiency_metrics.get("world_class_target", 0),
            },
        }

        return {"chart_data": chart_data, "tooling_family": tooling_family}

    except Exception as e:
        print(f"⚠️ Error generating chart data: {str(e)}")
        return {"chart_data": {}, "tooling_family": tooling_family}
