# Coverage comparison

The same 72 methods are present in every recorded run. Syntactic only = no-static*.csv; Static only = no-syntactic*.csv.

## Summary

| Measurement | Neither | Syntactic only | Static only | Both |
| --- | ---: | ---: | ---: | ---: |
| Recorded runs | 6 | 6 | 6 | 6 |
| Average instruction coverage | 78.90% ± 0.18 pp | 83.63% ± 0.10 pp | 79.79% ± 0.14 pp | 84.09% ± 0.00 pp |
| Average coverage: 17 Smith methods | 81.21% ± 0.77 pp | 83.30% ± 0.43 pp | 84.98% ± 0.57 pp | 85.21% ± 0.00 pp |
| Methods with higher mean coverage than neither | — | 18 | 4 | 19 |
| Methods with 100% coverage per run | 20.0 ± 0.0 | 22.0 ± 0.0 | 20.0 ± 0.0 | 22.0 ± 0.0 |
| Method–outcome pairs per run | 104.0 ± 0.0 | 122.7 ± 0.8 | 107.0 ± 0.0 | 124.3 ± 0.5 |
| Sum of recorded analysis times per run | 3.291 s ± 0.166 s | 5.100 s ± 0.455 s | 3.604 s ± 0.177 s | 4.683 s ± 0.261 s |

Each method has equal weight in average coverage. With repeated runs, values show mean ± sample standard deviation across runs; pp means percentage points. Summary deviations describe run-level totals or averages, not variation between methods, and are not confidence intervals.

Method–outcome pairs count each outcome once within each method and run, including `ok` and `*`. Results are averaged across runs, rather than combining discoveries from all repetitions. Recorded analysis times are summed; they are not the wall-clock duration of the JPAMB command.

## Instruction coverage by method

Only methods with different mean coverage between configurations are shown. Use --all-methods to include every method.

| Method | Neither | Syntactic only | Static only | Both |
| --- | ---: | ---: | ---: | ---: |
| Arrays.arrayNotEmpty:([I)V | 60.00% ± 0.00 pp | 70.00% ± 0.00 pp | 60.00% ± 0.00 pp | 70.00% ± 0.00 pp |
| Arrays.arraySpellsHello:([C)V | 40.62% ± 0.00 pp | 90.62% ± 0.00 pp | 40.62% ± 0.00 pp | 90.62% ± 0.00 pp |
| Arrays.binarySearch:(I)V | 92.75% ± 0.00 pp | 94.20% ± 0.00 pp | 92.75% ± 0.00 pp | 94.20% ± 0.00 pp |
| BitOperations.DrawInt:(I)V | 88.89% ± 0.00 pp | 91.67% ± 0.00 pp | 88.89% ± 0.00 pp | 91.67% ± 0.00 pp |
| BitOperations.bitshiftUnsignedRight:(I)V | 71.43% ± 0.00 pp | 78.57% ± 0.00 pp | 71.43% ± 0.00 pp | 78.57% ± 0.00 pp |
| Calls.allPrimesArePositive:(I)V | 7.69% ± 0.00 pp | 84.62% ± 0.00 pp | 7.69% ± 0.00 pp | 84.62% ± 0.00 pp |
| Calls.callsAssertFib:(I)V | 36.36% ± 0.00 pp | 72.73% ± 0.00 pp | 36.36% ± 0.00 pp | 72.73% ± 0.00 pp |
| Dependent.divisionLoop:(I)V | 80.95% ± 0.00 pp | 85.71% ± 0.00 pp | 80.95% ± 0.00 pp | 85.71% ± 0.00 pp |
| Dependent.normalizedDistance:(II)I | 93.10% ± 0.00 pp | 100.00% ± 0.00 pp | 93.10% ± 0.00 pp | 100.00% ± 0.00 pp |
| Dependent.safeDivByN:(I)I | 75.00% ± 0.00 pp | 100.00% ± 0.00 pp | 75.00% ± 0.00 pp | 100.00% ± 0.00 pp |
| Simple.assertInteger:(I)V | 55.56% ± 0.00 pp | 66.67% ± 0.00 pp | 55.56% ± 0.00 pp | 66.67% ± 0.00 pp |
| Simple.checkBeforeAssert:(I)V | 64.29% ± 0.00 pp | 78.57% ± 0.00 pp | 64.29% ± 0.00 pp | 78.57% ± 0.00 pp |
| Simple.checkBeforeDivideByN2:(I)I | 35.29% ± 0.00 pp | 76.47% ± 0.00 pp | 35.29% ± 0.00 pp | 76.47% ± 0.00 pp |
| Simple.checkBeforeDivideByN:(I)I | 66.67% ± 0.00 pp | 75.00% ± 0.00 pp | 66.67% ± 0.00 pp | 75.00% ± 0.00 pp |
| Strings.sayHello:(Ljava/lang/String;)V | 63.64% ± 0.00 pp | 72.73% ± 0.00 pp | 63.64% ± 0.00 pp | 72.73% ± 0.00 pp |
| Tricky.randomCompatibleBranches:(Ljpamb/utils/Smith;)V | 67.46% ± 9.72 pp | 76.19% ± 7.38 pp | 85.71% ± 0.00 pp | 85.71% ± 0.00 pp |
| Tricky.randomContradictoryBranches:(Ljpamb/utils/Smith;)V | 63.49% ± 12.30 pp | 71.43% ± 0.00 pp | 67.46% ± 9.72 pp | 71.43% ± 0.00 pp |
| Tricky.randomMaskedBranch:(Ljpamb/utils/Smith;)V | 62.50% ± 0.00 pp | 81.25% ± 0.00 pp | 81.25% ± 0.00 pp | 81.25% ± 0.00 pp |
| Tricky.randomShiftedBranch:(Ljpamb/utils/Smith;)V | 53.85% ± 0.00 pp | 53.85% ± 0.00 pp | 76.92% ± 0.00 pp | 76.92% ± 0.00 pp |

## Analysis time by method

Mean ± sample standard deviation, in milliseconds.

| Method | Neither | Syntactic only | Static only | Both |
| --- | ---: | ---: | ---: | ---: |
| Arrays.arrayContent:()V | 2.13 ms ± 0.11 ms | 5.22 ms ± 0.53 ms | 2.57 ms ± 0.27 ms | 10.74 ms ± 11.47 ms |
| Arrays.arrayContentAboveMinus13:()V | 2.45 ms ± 0.37 ms | 5.20 ms ± 0.60 ms | 2.66 ms ± 0.25 ms | 5.06 ms ± 0.28 ms |
| Arrays.arrayInBounds:()V | 1.73 ms ± 0.41 ms | 4.46 ms ± 0.60 ms | 1.76 ms ± 0.12 ms | 4.41 ms ± 0.27 ms |
| Arrays.arrayIsNull:()V | 1.52 ms ± 0.19 ms | 4.26 ms ± 0.22 ms | 1.51 ms ± 0.10 ms | 4.07 ms ± 0.42 ms |
| Arrays.arrayIsNullLength:()V | 1.57 ms ± 0.11 ms | 4.23 ms ± 0.41 ms | 1.64 ms ± 0.15 ms | 4.12 ms ± 0.44 ms |
| Arrays.arrayLength:()V | 1.79 ms ± 0.10 ms | 4.75 ms ± 0.41 ms | 2.05 ms ± 0.25 ms | 4.30 ms ± 0.38 ms |
| Arrays.arrayNotEmpty:([I)V | 12.72 ms ± 0.80 ms | 18.83 ms ± 1.22 ms | 13.86 ms ± 1.20 ms | 18.72 ms ± 0.68 ms |
| Arrays.arrayOutOfBounds:()V | 1.68 ms ± 0.27 ms | 4.59 ms ± 0.76 ms | 1.78 ms ± 0.29 ms | 4.09 ms ± 0.22 ms |
| Arrays.arraySometimesNull:(I)V | 4.33 ms ± 0.44 ms | 15.34 ms ± 1.64 ms | 4.66 ms ± 0.50 ms | 15.15 ms ± 2.39 ms |
| Arrays.arraySpellsHello:([C)V | 13.23 ms ± 0.45 ms | 21.83 ms ± 0.68 ms | 15.35 ms ± 1.10 ms | 22.39 ms ± 0.76 ms |
| Arrays.arraySumIsLarge:([I)V | 933.31 ms ± 74.30 ms | 1052.24 ms ± 74.26 ms | 955.33 ms ± 79.87 ms | 962.40 ms ± 35.16 ms |
| Arrays.binarySearch:(I)V | 31.72 ms ± 4.89 ms | 207.29 ms ± 25.30 ms | 28.87 ms ± 0.62 ms | 188.30 ms ± 8.88 ms |
| BitOperations.DrawInt:(I)V | 299.18 ms ± 3.85 ms | 376.87 ms ± 43.14 ms | 300.28 ms ± 10.98 ms | 351.93 ms ± 15.08 ms |
| BitOperations.bitshiftLeft:(I)V | 3.59 ms ± 0.43 ms | 12.78 ms ± 1.51 ms | 3.63 ms ± 0.28 ms | 11.77 ms ± 0.75 ms |
| BitOperations.bitshiftRight:(I)V | 3.59 ms ± 0.35 ms | 12.20 ms ± 0.50 ms | 3.83 ms ± 0.36 ms | 12.88 ms ± 1.67 ms |
| BitOperations.bitshiftUnsignedRight:(I)V | 3.95 ms ± 0.97 ms | 13.97 ms ± 2.30 ms | 3.95 ms ± 0.48 ms | 11.73 ms ± 1.04 ms |
| BitOperations.bitwiseAnd:(II)V | 7.57 ms ± 0.87 ms | 29.68 ms ± 4.11 ms | 7.89 ms ± 0.41 ms | 26.78 ms ± 1.24 ms |
| BitOperations.bitwiseNot:(I)V | 3.58 ms ± 0.17 ms | 13.09 ms ± 1.95 ms | 4.14 ms ± 0.82 ms | 11.86 ms ± 0.46 ms |
| BitOperations.bitwiseOr:(II)V | 8.18 ms ± 0.36 ms | 49.33 ms ± 2.57 ms | 9.38 ms ± 1.27 ms | 46.96 ms ± 2.05 ms |
| BitOperations.xor:(II)V | 7.28 ms ± 0.29 ms | 30.17 ms ± 3.14 ms | 7.77 ms ± 0.38 ms | 27.45 ms ± 1.35 ms |
| Calls.allPrimesArePositive:(I)V | 4.56 ms ± 0.40 ms | 115.83 ms ± 9.65 ms | 4.69 ms ± 0.46 ms | 108.29 ms ± 5.13 ms |
| Calls.callsAssertFalse:()V | 1.69 ms ± 0.17 ms | 4.75 ms ± 0.91 ms | 1.80 ms ± 0.12 ms | 4.00 ms ± 0.36 ms |
| Calls.callsAssertFib:(I)V | 280.67 ms ± 20.63 ms | 489.50 ms ± 80.20 ms | 286.85 ms ± 17.55 ms | 417.01 ms ± 22.97 ms |
| Calls.callsAssertIf:(Z)V | 3.65 ms ± 0.12 ms | 11.08 ms ± 2.99 ms | 4.00 ms ± 0.29 ms | 9.21 ms ± 0.53 ms |
| Calls.callsAssertIfWithTrue:()V | 2.24 ms ± 0.14 ms | 5.51 ms ± 1.02 ms | 2.50 ms ± 0.43 ms | 4.56 ms ± 0.27 ms |
| Calls.callsAssertTrue:()V | 1.61 ms ± 0.10 ms | 5.00 ms ± 0.78 ms | 1.73 ms ± 0.14 ms | 3.93 ms ± 0.40 ms |
| Dependent.badNormalizedDistance:(II)I | 13.31 ms ± 0.55 ms | 46.87 ms ± 5.14 ms | 15.45 ms ± 4.01 ms | 42.85 ms ± 1.22 ms |
| Dependent.divisionLoop:(I)V | 13.13 ms ± 0.39 ms | 62.07 ms ± 7.33 ms | 13.68 ms ± 0.60 ms | 55.39 ms ± 3.21 ms |
| Dependent.normalizedDistance:(II)I | 14.85 ms ± 1.10 ms | 51.02 ms ± 6.16 ms | 14.72 ms ± 0.62 ms | 45.68 ms ± 1.37 ms |
| Dependent.safeDivByN:(I)I | 2.43 ms ± 0.33 ms | 9.67 ms ± 0.95 ms | 2.41 ms ± 0.17 ms | 8.75 ms ± 0.41 ms |
| Loops.forever:()V | 0.71 ms ± 0.06 ms | 2.99 ms ± 0.31 ms | 0.80 ms ± 0.09 ms | 3.33 ms ± 0.75 ms |
| Loops.neverAsserts:()V | 0.88 ms ± 0.10 ms | 3.25 ms ± 0.34 ms | 0.99 ms ± 0.09 ms | 2.86 ms ± 0.09 ms |
| Loops.neverDivides:()I | 0.85 ms ± 0.10 ms | 2.93 ms ± 0.32 ms | 0.89 ms ± 0.10 ms | 2.78 ms ± 0.16 ms |
| Loops.terminates:()V | 1.05 ms ± 0.17 ms | 3.31 ms ± 0.44 ms | 1.18 ms ± 0.15 ms | 3.06 ms ± 0.49 ms |
| Randomness.branchOverlap:(Ljpamb/utils/Smith;)V | 58.30 ms ± 2.90 ms | 80.94 ms ± 4.91 ms | 61.62 ms ± 2.60 ms | 79.77 ms ± 1.84 ms |
| Randomness.compareInts:(Ljpamb/utils/Smith;)V | 54.35 ms ± 2.99 ms | 71.70 ms ± 4.38 ms | 58.82 ms ± 1.27 ms | 69.50 ms ± 2.11 ms |
| Randomness.draw34Bits:(Ljpamb/utils/Smith;)V | 36.41 ms ± 1.17 ms | 47.31 ms ± 3.91 ms | 40.27 ms ± 1.44 ms | 46.05 ms ± 1.39 ms |
| Randomness.drawDependsOnArg:(ILjpamb/utils/Smith;)I | 27.76 ms ± 0.77 ms | 43.05 ms ± 2.55 ms | 30.71 ms ± 1.07 ms | 42.71 ms ± 1.16 ms |
| Randomness.drawInCallee:(Ljpamb/utils/Smith;)V | 28.29 ms ± 1.47 ms | 38.02 ms ± 4.16 ms | 31.32 ms ± 1.52 ms | 36.23 ms ± 0.83 ms |
| Randomness.drawInt:(Ljpamb/utils/Smith;)V | 67.50 ms ± 3.38 ms | 146.33 ms ± 30.77 ms | 71.34 ms ± 3.64 ms | 135.26 ms ± 4.76 ms |
| Randomness.drawIntOverflow:(Ljpamb/utils/Smith;)V | 45.33 ms ± 5.21 ms | 52.42 ms ± 3.33 ms | 45.33 ms ± 1.01 ms | 49.60 ms ± 1.99 ms |
| Randomness.loopUntilHeads:(Ljpamb/utils/Smith;)V | 687.51 ms ± 147.15 ms | 883.73 ms ± 149.92 ms | 861.03 ms ± 136.58 ms | 791.71 ms ± 155.41 ms |
| Randomness.randomBranch:(Ljpamb/utils/Smith;)V | 23.61 ms ± 2.29 ms | 32.42 ms ± 4.34 ms | 25.42 ms ± 0.84 ms | 30.94 ms ± 2.37 ms |
| Randomness.randomIndex:(Ljpamb/utils/Smith;)V | 32.69 ms ± 1.06 ms | 43.83 ms ± 3.41 ms | 37.04 ms ± 2.03 ms | 42.38 ms ± 1.61 ms |
| Randomness.randomNull:(Ljpamb/utils/Smith;)V | 32.53 ms ± 7.81 ms | 37.74 ms ± 3.79 ms | 33.29 ms ± 1.55 ms | 38.94 ms ± 1.50 ms |
| Randomness.spinOnTails:(Ljpamb/utils/Smith;)V | 23.45 ms ± 3.97 ms | 32.50 ms ± 4.61 ms | 24.60 ms ± 0.81 ms | 28.62 ms ± 0.92 ms |
| Randomness.twoDraws:(Ljpamb/utils/Smith;)V | 36.36 ms ± 3.23 ms | 43.25 ms ± 3.52 ms | 40.75 ms ± 7.74 ms | 43.86 ms ± 2.64 ms |
| Simple.assertBoolean:(Z)V | 1.73 ms ± 0.19 ms | 7.54 ms ± 0.62 ms | 1.87 ms ± 0.16 ms | 8.63 ms ± 2.83 ms |
| Simple.assertFalse:()V | 1.11 ms ± 0.14 ms | 3.76 ms ± 0.51 ms | 1.18 ms ± 0.11 ms | 3.72 ms ± 0.66 ms |
| Simple.assertInteger:(I)V | 2.73 ms ± 0.59 ms | 12.08 ms ± 1.59 ms | 2.62 ms ± 0.21 ms | 9.65 ms ± 0.76 ms |
| Simple.assertPositive:(I)V | 2.50 ms ± 0.27 ms | 10.96 ms ± 1.39 ms | 2.50 ms ± 0.21 ms | 9.47 ms ± 0.72 ms |
| Simple.assertTrue:()V | 1.04 ms ± 0.23 ms | 3.74 ms ± 0.51 ms | 0.99 ms ± 0.12 ms | 3.38 ms ± 0.41 ms |
| Simple.checkBeforeAssert:(I)V | 3.21 ms ± 0.17 ms | 11.54 ms ± 0.90 ms | 3.71 ms ± 1.13 ms | 10.79 ms ± 0.76 ms |
| Simple.checkBeforeDivideByN2:(I)I | 2.76 ms ± 0.18 ms | 10.53 ms ± 0.90 ms | 2.94 ms ± 0.29 ms | 10.28 ms ± 0.67 ms |
| Simple.checkBeforeDivideByN:(I)I | 3.39 ms ± 0.43 ms | 12.31 ms ± 1.89 ms | 3.26 ms ± 0.46 ms | 10.37 ms ± 0.35 ms |
| Simple.divideByN:(I)I | 2.35 ms ± 0.33 ms | 10.16 ms ± 0.67 ms | 2.49 ms ± 0.33 ms | 9.40 ms ± 0.71 ms |
| Simple.divideByNMinus10054203:(I)I | 2.68 ms ± 0.24 ms | 14.04 ms ± 0.84 ms | 2.84 ms ± 0.32 ms | 13.55 ms ± 0.88 ms |
| Simple.divideByZero:()I | 1.12 ms ± 0.12 ms | 3.82 ms ± 1.18 ms | 1.19 ms ± 0.13 ms | 3.65 ms ± 0.25 ms |
| Simple.divideZeroByZero:(II)I | 4.55 ms ± 0.82 ms | 18.34 ms ± 3.48 ms | 4.53 ms ± 0.69 ms | 16.43 ms ± 0.98 ms |
| Simple.doNothing:()V | 0.99 ms ± 0.06 ms | 3.99 ms ± 0.95 ms | 1.06 ms ± 0.23 ms | 3.47 ms ± 0.24 ms |
| Simple.earlyReturn:()I | 1.03 ms ± 0.12 ms | 3.88 ms ± 0.62 ms | 1.28 ms ± 0.24 ms | 3.37 ms ± 0.35 ms |
| Simple.justAdd:(II)I | 4.31 ms ± 0.68 ms | 20.04 ms ± 4.84 ms | 4.49 ms ± 0.56 ms | 16.36 ms ± 0.70 ms |
| Simple.justMulitply:(II)I | 4.23 ms ± 0.27 ms | 20.97 ms ± 6.96 ms | 5.25 ms ± 1.66 ms | 16.95 ms ± 1.16 ms |
| Simple.justReturn:()I | 1.06 ms ± 0.18 ms | 5.15 ms ± 2.03 ms | 1.04 ms ± 0.13 ms | 3.48 ms ± 0.37 ms |
| Simple.justReturnNothing:()V | 0.97 ms ± 0.12 ms | 4.12 ms ± 0.82 ms | 1.06 ms ± 0.09 ms | 3.30 ms ± 0.28 ms |
| Simple.multiError:(Z)I | 1.86 ms ± 0.15 ms | 7.88 ms ± 1.08 ms | 2.01 ms ± 0.36 ms | 7.14 ms ± 0.23 ms |
| Strings.sayHello:(Ljava/lang/String;)V | 3.94 ms ± 0.11 ms | 9.66 ms ± 1.63 ms | 8.81 ms ± 11.24 ms | 9.00 ms ± 1.60 ms |
| Tricky.collatz:(I)V | 238.53 ms ± 36.06 ms | 436.68 ms ± 70.20 ms | 267.01 ms ± 69.93 ms | 407.92 ms ± 51.89 ms |
| Tricky.randomCompatibleBranches:(Ljpamb/utils/Smith;)V | 38.85 ms ± 3.08 ms | 49.89 ms ± 4.58 ms | 48.61 ms ± 3.92 ms | 51.82 ms ± 1.83 ms |
| Tricky.randomContradictoryBranches:(Ljpamb/utils/Smith;)V | 40.36 ms ± 2.52 ms | 61.86 ms ± 35.95 ms | 47.43 ms ± 7.29 ms | 50.84 ms ± 3.10 ms |
| Tricky.randomMaskedBranch:(Ljpamb/utils/Smith;)V | 39.06 ms ± 2.19 ms | 47.63 ms ± 4.04 ms | 45.18 ms ± 3.25 ms | 48.95 ms ± 2.88 ms |
| Tricky.randomShiftedBranch:(Ljpamb/utils/Smith;)V | 46.16 ms ± 1.84 ms | 56.47 ms ± 8.41 ms | 54.66 ms ± 4.88 ms | 58.59 ms ± 3.92 ms |

These tables are descriptive comparisons. One recorded run does not measure run-to-run variation; repeated runs must be genuine separate executions, not duplicate copies of the same result.
