Param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

python -m noty.cli setup @Args
