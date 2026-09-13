
RANGE_CHECK_CRITERIA = """
Does the retrieval context contain information that is relevant to answering
the numeric value or time period mentioned in the input?

Specifically: if the input mentions a specific number (e.g. '3 days', '7 days'),
and the retrieval context states a RANGE or THRESHOLD that the input's number
falls within (e.g. 'within 5 days', 'more than 5 days and up to 10 days'),
this counts as YES — the context IS relevant, because the range/threshold
governs that specific value.

Example 1: Input asks about '3 days'. Context states 'within 5 days qualifies
for 100% refund'. Since 3 is within the 0-5 day range, this is YES (relevant).

Example 2: Input asks about '7 days'. Context states 'more than 5 days and up
to 10 days qualifies for 50% refund'. Since 7 falls within the 5-10 day range,
this is YES (relevant).

Only answer NO if the context's numeric range genuinely does NOT contain the
input's value, or if the context is about a completely unrelated topic.

IMPORTANT: A value is considered "within" a range if it is greater than the 
lower bound and less than or equal to the upper bound (or falls anywhere 
strictly between the bounds). Do NOT treat values in the middle of a range 
as boundary cases requiring special caution. For example, 7 is clearly and 
unambiguously within the range 'more than 5 and up to 10' — there is no 
ambiguity here, answer YES directly without hedging.
"""