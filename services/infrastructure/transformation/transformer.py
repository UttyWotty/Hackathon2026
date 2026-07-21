"""
Data Transformation Engine.

Features:
- Column operations (rename, select, drop)
- Data type conversions
- Aggregations
- Pivoting/unpivoting
- Filtering
- Sorting
- Custom transformations

Author: Utku Gulbardak
Date: 2025-11-12
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import pandas as pd

logger = logging.getLogger(__name__)


class DataTransformer:
    """
    Data Transformation Engine.

    Provides various data transformation capabilities.
    """

    def __init__(self):
        """Initialize Data Transformer."""
        self.stats = {
            "transformations_performed": 0,
            "rows_transformed": 0,
            "columns_transformed": 0,
        }
        logger.info("✅ Data Transformer initialized")

    def select_columns(
        self, df: pd.DataFrame, columns: List[str]
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Select specific columns from DataFrame.

        Args:
            df: Input DataFrame
            columns: List of column names to keep

        Returns:
            tuple: (transformed DataFrame, statistics)
        """
        missing_cols = [col for col in columns if col not in df.columns]
        existing_cols = [col for col in columns if col in df.columns]

        df_result = df[existing_cols]

        self.stats["transformations_performed"] += 1

        return df_result, {
            "requested_columns": len(columns),
            "selected_columns": len(existing_cols),
            "missing_columns": missing_cols if missing_cols else None,
        }

    def rename_columns(
        self, df: pd.DataFrame, mapping: Dict[str, str]
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Rename DataFrame columns.

        Args:
            df: Input DataFrame
            mapping: Dict of {old_name: new_name}

        Returns:
            tuple: (transformed DataFrame, statistics)
        """
        df_result = df.rename(columns=mapping)

        self.stats["transformations_performed"] += 1
        self.stats["columns_transformed"] += len(mapping)

        return df_result, {
            "columns_renamed": len(mapping),
            "mapping": mapping,
        }

    def convert_dtypes(
        self, df: pd.DataFrame, conversions: Dict[str, str]
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Convert column data types.

        Args:
            df: Input DataFrame
            conversions: Dict of {column: target_type}
                        Types: 'int', 'float', 'str', 'datetime', 'bool'

        Returns:
            tuple: (transformed DataFrame, statistics)
        """
        df_result = df.copy()
        conversion_report = {}

        for col, target_type in conversions.items():
            if col not in df.columns:
                conversion_report[col] = {
                    "status": "error",
                    "error": "Column not found",
                }
                continue

            try:
                if target_type == "int":
                    df_result[col] = pd.to_numeric(
                        df_result[col], errors="coerce"
                    ).astype("Int64")
                elif target_type == "float":
                    df_result[col] = pd.to_numeric(df_result[col], errors="coerce")
                elif target_type == "str":
                    df_result[col] = df_result[col].astype(str)
                elif target_type == "datetime":
                    df_result[col] = pd.to_datetime(df_result[col], errors="coerce")
                elif target_type == "bool":
                    df_result[col] = df_result[col].astype(bool)
                else:
                    conversion_report[col] = {
                        "status": "error",
                        "error": f"Unknown type: {target_type}",
                    }
                    continue

                conversion_report[col] = {
                    "status": "success",
                    "from_type": str(df[col].dtype),
                    "to_type": str(df_result[col].dtype),
                }

            except Exception as e:
                conversion_report[col] = {"status": "error", "error": str(e)}

        self.stats["transformations_performed"] += 1
        self.stats["columns_transformed"] += len(conversions)

        return df_result, {
            "conversions_attempted": len(conversions),
            "conversion_details": conversion_report,
        }

    def filter_rows(
        self,
        df: pd.DataFrame,
        conditions: Union[str, List[Dict[str, Any]]],
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Filter DataFrame rows.

        Args:
            df: Input DataFrame
            conditions: Query string (e.g., "age > 25 and city == 'NYC'")
                       or list of dicts [{column, operator, value}]

        Returns:
            tuple: (filtered DataFrame, statistics)
        """
        original_count = len(df)

        if isinstance(conditions, str):
            # Query string
            df_result = df.query(conditions)
        else:
            # List of conditions
            mask = pd.Series([True] * len(df), index=df.index)

            for cond in conditions:
                col = cond.get("column")
                op = cond.get("operator")
                value = cond.get("value")

                if col not in df.columns:
                    logger.warning(f"Column '{col}' not found, skipping condition")
                    continue

                if op == "==":
                    mask &= df[col] == value
                elif op == "!=":
                    mask &= df[col] != value
                elif op == ">":
                    mask &= df[col] > value
                elif op == ">=":
                    mask &= df[col] >= value
                elif op == "<":
                    mask &= df[col] < value
                elif op == "<=":
                    mask &= df[col] <= value
                elif op == "in":
                    mask &= df[col].isin(value)
                elif op == "not_in":
                    mask &= ~df[col].isin(value)
                elif op == "contains":
                    mask &= df[col].str.contains(value, na=False)
                else:
                    logger.warning(f"Unknown operator '{op}', skipping condition")

            df_result = df[mask]

        self.stats["transformations_performed"] += 1
        self.stats["rows_transformed"] += original_count - len(df_result)

        return df_result, {
            "original_rows": original_count,
            "filtered_rows": len(df_result),
            "rows_removed": original_count - len(df_result),
            "filter_percentage": (
                round((original_count - len(df_result)) / original_count * 100, 2)
                if original_count > 0
                else 0
            ),
        }

    def aggregate_data(
        self,
        df: pd.DataFrame,
        group_by: List[str],
        aggregations: Dict[str, Union[str, List[str]]],
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Aggregate DataFrame.

        Args:
            df: Input DataFrame
            group_by: Columns to group by
            aggregations: Dict of {column: aggregation_function(s)}
                         Functions: 'sum', 'mean', 'median', 'min', 'max', 'count', 'std'

        Returns:
            tuple: (aggregated DataFrame, statistics)
        """
        original_rows = len(df)

        df_result = df.groupby(group_by).agg(aggregations).reset_index()

        self.stats["transformations_performed"] += 1
        self.stats["rows_transformed"] += original_rows

        return df_result, {
            "original_rows": original_rows,
            "aggregated_rows": len(df_result),
            "group_by_columns": group_by,
            "aggregation_count": len(aggregations),
            "reduction_ratio": (
                round(original_rows / len(df_result), 2) if len(df_result) > 0 else 0
            ),
        }

    def pivot_data(
        self,
        df: pd.DataFrame,
        index: Union[str, List[str]],
        columns: str,
        values: str,
        aggfunc: str = "mean",
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Pivot DataFrame.

        Args:
            df: Input DataFrame
            index: Column(s) to use as index
            columns: Column to pivot
            values: Column to aggregate
            aggfunc: Aggregation function

        Returns:
            tuple: (pivoted DataFrame, statistics)
        """
        original_shape = df.shape

        df_result = df.pivot_table(
            index=index, columns=columns, values=values, aggfunc=aggfunc
        ).reset_index()

        self.stats["transformations_performed"] += 1

        return df_result, {
            "original_shape": original_shape,
            "pivoted_shape": df_result.shape,
            "index_columns": index if isinstance(index, list) else [index],
            "pivot_column": columns,
            "value_column": values,
        }

    def sort_data(
        self,
        df: pd.DataFrame,
        by: Union[str, List[str]],
        ascending: Union[bool, List[bool]] = True,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Sort DataFrame.

        Args:
            df: Input DataFrame
            by: Column(s) to sort by
            ascending: Sort order(s)

        Returns:
            tuple: (sorted DataFrame, statistics)
        """
        df_result = df.sort_values(by=by, ascending=ascending).reset_index(drop=True)

        self.stats["transformations_performed"] += 1

        return df_result, {
            "rows_sorted": len(df_result),
            "sort_columns": by if isinstance(by, list) else [by],
            "ascending": ascending,
        }

    def merge_dataframes(
        self,
        left: pd.DataFrame,
        right: pd.DataFrame,
        on: Optional[Union[str, List[str]]] = None,
        left_on: Optional[Union[str, List[str]]] = None,
        right_on: Optional[Union[str, List[str]]] = None,
        how: str = "inner",
        suffixes: Tuple[str, str] = ("_left", "_right"),
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Merge two DataFrames.

        Args:
            left: Left DataFrame
            right: Right DataFrame
            on: Column(s) to join on (for both)
            left_on: Column(s) to join on (left)
            right_on: Column(s) to join on (right)
            how: 'inner', 'outer', 'left', 'right'
            suffixes: Suffixes for overlapping columns

        Returns:
            tuple: (merged DataFrame, statistics)
        """
        df_result = pd.merge(
            left=left,
            right=right,
            on=on,
            left_on=left_on,
            right_on=right_on,
            how=how,
            suffixes=suffixes,
        )

        self.stats["transformations_performed"] += 1

        return df_result, {
            "left_rows": len(left),
            "right_rows": len(right),
            "merged_rows": len(df_result),
            "merge_type": how,
            "join_columns": on or {"left": left_on, "right": right_on},
        }

    def apply_custom_function(
        self,
        df: pd.DataFrame,
        column: str,
        func: Callable,
        new_column: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Apply custom function to column.

        Args:
            df: Input DataFrame
            column: Column to apply function to
            func: Function to apply
            new_column: Name for new column (None = overwrite original)

        Returns:
            tuple: (transformed DataFrame, statistics)
        """
        df_result = df.copy()

        target_col = new_column if new_column else column

        df_result[target_col] = df[column].apply(func)

        self.stats["transformations_performed"] += 1

        return df_result, {
            "source_column": column,
            "target_column": target_col,
            "rows_transformed": len(df_result),
        }

    def add_calculated_column(
        self,
        df: pd.DataFrame,
        new_column: str,
        expression: str,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Add calculated column using expression.

        Args:
            df: Input DataFrame
            new_column: Name for new column
            expression: Calculation expression (e.g., "col1 + col2 * 2")

        Returns:
            tuple: (transformed DataFrame, statistics)
        """
        df_result = df.copy()

        # Evaluate expression
        df_result[new_column] = df.eval(expression)

        self.stats["transformations_performed"] += 1

        return df_result, {
            "new_column": new_column,
            "expression": expression,
            "rows_transformed": len(df_result),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get transformer statistics."""
        return {
            "status": "success",
            **self.stats,
        }


# Global data transformer instance
_data_transformer: Optional[DataTransformer] = None


def get_data_transformer() -> DataTransformer:
    """
    Get global data transformer instance.

    Returns:
        DataTransformer: Global data transformer instance
    """
    global _data_transformer
    if _data_transformer is None:
        _data_transformer = DataTransformer()
    return _data_transformer
