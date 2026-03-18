# GraphDistill 搜索优化测试报告

> 生成时间：2026-03-17 18:13:07

本报告涵盖两个核心数据源的知识检索测试：
- **Cangjie_StdLib**：`cangjie_runtime.git` (branch: release/1.0, subdir: std/doc/libs)
- **interface_sdk_cangjie**：`interface_sdk_cangjie.git` (branch: master, subdir: api)
- 测试用例覆盖：std.core, std.collection, std.math, std.sync, std.time, std.io, std.regex, ArkUI 组件 (Button/Text/Grid/List/Row), Ark Interop (JSArrayBuffer)

## 1. 知识图谱概览

| 指标 | 值 |
|------|-----|
| 实体数量 | 12726 |
| 关系数量 | 19871 |
| 弱连通分量数 | 1435 |
| 向量索引 | ✅ 已构建 |
| Embedding 模型 | Qwen/Qwen3-Embedding-8B |

## 2. 图结构验证

通过 13/13 项结构验证。

| 测试类型 | 通过 | 详情 |
|----------|------|------|
| entity_group_std核心概念 | ✅ | std核心概念: 9/9 found |
| entity_group_std集合类 | ✅ | std集合类: 7/7 found |
| entity_group_std并发类 | ✅ | std并发类: 2/2 found |
| entity_group_SDK ArkUI 组件 | ✅ | SDK ArkUI 组件: 4/4 found |
| documented_at_count | ✅ | DOCUMENTED_AT edges: 1288, File entities: 203 |
| key_concept_documented_at | ✅ | 6/6 key concepts have DOCUMENTED_AT links |
| entity_type_distribution | ✅ | Entity types (17): {'Function': 6005, 'Concept': 1754, 'Property': 1206, 'Class': 1185, 'CodeSnippet': 996, 'Interface': 394, 'Enum': 321, 'Struct': 224, 'File': 203, 'Exception': 120} |
| relation_type_distribution | ✅ | Relation types (14): {'RETURNS': 5907, 'ACCEPTS_PARAM': 5060, 'BELONGS_TO': 2488, 'DOCUMENTED_AT': 1288, 'THROWS': 1248, 'IMPLEMENTS': 1002, 'HAS_SAMPLE_CODE': 931, 'MODIFIED_BY': 554, 'CONTAINS': 529, 'DEPENDS_ON': 305} |
| source_distribution | ✅ | Source presets: {'Cangjie_StdLib': 9883, 'interface_sdk_cangjie': 2843} |
| min_relation_count_BELONGS_TO | ✅ | BELONGS_TO: 2488 (min expected: 100) |
| min_relation_count_INHERITS | ✅ | INHERITS: 290 (min expected: 10) |
| min_relation_count_IMPLEMENTS | ✅ | IMPLEMENTS: 1002 (min expected: 50) |
| min_relation_count_RETURNS | ✅ | RETURNS: 5907 (min expected: 100) |

## 2.5 文档目录引用（DOCUMENTED_AT）功能测试

验证搜索引擎能否通过 DOCUMENTED_AT 关系找到关联的文档路径，用于增强搜索上下文。

**通过率**: 8/8

| ID | 描述 | 通过 | 文档引用数 | 示例引用 |
|----|------|------|-----------|---------|
| docref_01 | core 概念应有文档引用 | ✅ | 1 (min=1) | core→./core/core_package_overview.md |
| docref_02 | collection 概念应有文档引用 | ✅ | 2 (min=1) | collection→./collection/collection_package_overview.md \| collection→./core_package_api/core_package_interfaces.md |
| docref_03 | math 概念应有文档引用 | ✅ | 1 (min=1) | math→./math/math_package_overview.md |
| docref_04 | sync 概念应有文档引用 | ✅ | 1 (min=1) | sync→./sync/sync_package_overview.md |
| docref_05 | time 概念应有文档引用 | ✅ | 1 (min=1) | time→./time/time_package_overview.md |
| docref_06 | io 概念应有文档引用 | ✅ | 1 (min=1) | io→./io/io_package_overview.md |
| docref_07 | 集合类概念（混合查询）应有文档引用 | ✅ | 2 (min=1) | HashMap→./collection_package_api/collection_package_class.md \| ArrayList→../../collection/collection_package_api/collection_package_class.md |
| docref_08 | regex 概念应有文档引用 | ✅ | 2 (min=1) | regex→./regex/regex_package_overview.md \| regex→./regex_package_api/regex_package_classes.md |

## 3. 关键词回退检索测试（无 LLM）

验证在向量索引不可用时，关键词回退逻辑（`_keyword_fallback_candidates`）能否定位到正确的图谱实体。

**通过率**: 13/13

| ID | 问题 | 通过 | 期望关键词 | 命中 | Top-3候选实体 |
|----|------|------|-----------|------|--------------|
| kw_01 | 怎么将字符串中的浮点数转为Float64类型？ | ✅ | float64 | float64 | struct:std_core_float64(d=0.01) \| type:std_core_float64(d=0.01) \| type:float64(d=0.01) |
| kw_02 | IncompatiblePackageException 在什么场景下会被抛出？ | ✅ | incompatiblepackageexception | incompatiblepackageexception | concept:incompatiblepackageexception(d=0.01) \| class:incompatiblepackageexception(d=0.01) \| function:incompatiblepackageexception_init(d=4.01) |
| kw_03 | 仓颉语言中如何使用 ArrayList 存储和遍历元素？ | ✅ | arraylist | arraylist | class:std_ast_arraylist(d=0.01) \| class:arraylist(d=1.01) \| class:std_collection_arraylist(d=1.01) |
| kw_04 | HashMap 如何存储和查找键值对？ | ✅ | hashmap | hashmap | class:std_collection_hashmap(d=0.01) \| concept:hashmap(d=1.01) \| struct:std_collection_hashmap(d=1.01) |
| kw_05 | ArrayDeque 双端队列的容量策略是怎样的？ | ✅ | arraydeque | arraydeque | class:std_collection_arraydeque(d=0.01) \| class:arraydeque(d=4.01) \| concept:arraydeque(d=5.01) |
| kw_06 | TreeMap 和 TreeSet 的底层实现是什么？ | ✅ | treemap | treemap | class:std_collection_treemap(d=1.01) \| concept:treemap(d=2.01) \| function:std_collection_treemap_removeif(d=6.01) |
| kw_07 | AtomicInt64 原子操作支持哪些方法？ | ✅ | atomicint64 | atomicint64 | class:std_sync_atomicint64(d=0.01) \| class:atomicint64(d=2.01) \| concept:atomicint64(d=3.01) |
| kw_08 | 如何使用 Mutex 互斥锁？ | ✅ | mutex | mutex | class:std_sync_mutex(d=0.01) \| class:mutex(d=1.01) \| concept:mutex(d=2.01) |
| kw_09 | DateTime 如何解析时间字符串？ | ✅ | datetime | datetime | concept:时间字符串格式(d=0.01) \| struct:std_time_datetime(d=3.01) \| class:std_time_datetime(d=3.01) |
| kw_10 | BufferedInputStream 的作用是什么？ | ✅ | bufferedinputstream | bufferedinputstream | class:std_io_bufferedinputstream(d=0.01) \| class:bufferedinputstream(d=0.01) \| function:std_io_bufferedinputstream_init(d=5.01) |
| kw_11 | Button 组件有哪些类型？ | ✅ | button | button | class:buttoninfo(d=0.01) \| class:alertdialogbuttonbaseoptions(d=0.01) \| class:buttonoptions(d=0.01) |
| kw_12 | Grid 组件如何设定列模板？ | ✅ | grid | grid | class:grid(d=0.01) \| class:scrollablecommonmethodcomponent(d=5.01) \| class:gridcoloptions(d=5.01) |
| kw_13 | JSArrayBuffer 类提供了哪些方法？ | ✅ | jsarraybuffer | jsarraybuffer | class:jsarraybuffer(d=0.01) \| class:std_unittest_benchmark(d=6.01) \| class:std_unittest_mock_setteractionselector(d=6.01) |

## 4. 搜索问答测试结果
### 4.1 详细测试结果

#### [stdlib_core_01] ✅ PASS

**问题**：怎么将字符串中的浮点数转为Float64类型？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：40.16% | **关键词覆盖率**：100% | **响应时间**：29.42s
**匹配实体**：`function:std_convert_float64_parse`(d=0.5101), `struct:std_float64`(d=0.5211), `function:std_math_numeric_decimal_tofloat64`(d=0.5558)
**实体路由命中**：float64
**命中关键词**：Float64, parse, 字符串
**文档目录引用**（2 条）：
  - 「Float64」→ ./core_package_api/core_package_intrinsics.md
  - 「Float64」→ ../../core/core_package_api/core_package_intrinsics.md

**回答**：

> 基于提供的图上下文，可以使用 `std.convert` 模块中的以下函数将字符串转换为 Float64 类型：
>
> *   **Float64.parse**：将字符串解析为 Float64 类型。
> *   **Float64.tryParse**：尝试将字符串解析为 Float64 类型。

#### [stdlib_core_02] ✅ PASS

**问题**：std.core 包中 String 类有哪些常用方法？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：37.78% | **关键词覆盖率**：100% | **响应时间**：48.96s
**匹配实体**：`class:std_string`(d=0.7467), `file:__core_package_api_core_package_intrinsics_md`(d=0.7785), `class:core_string`(d=0.8154)
**实体路由命中**：string
**命中关键词**：String, core
**文档目录引用**（7 条）：
  - 「String」→ ./core_package_api/core_package_structs.md
  - 「String」→ ../../core/core_package_api/core_package_structs.md
  - 「StringBuilder」→ ./core_package_api/core_package_classes.md
  - 「Unit」→ ./core_package_api/core_package_intrinsics.md
  - 「Int64」→ ../../core/core_package_api/core_package_intrinsics.md

**回答**：

> 基于提供的图上下文，`std.core` 包中的 `String` 类（或结构体）提供了以下常用方法，涵盖构造、查询、比较、修剪、转换及连接等功能：
>
> **1. 构造方法**
> *   **`fromUtf8`**: 静态方法，根据 UTF-8 编码的字节数组（`Array<UInt8>`）构造一个字符串。如果入参不符合 UTF-8 序列规则或长度超过限制，会抛出 `IllegalArgumentException`。
> *   **`fromUtf8Unchecked`**: 静态方法，根据字节数组构造一个字符串，但不进行 UTF-8 规则检查（Unsafe 操作）。
>
> **2. 查询与搜索**
> *   **`indexOf`**: 获取指定字节或字符串第一次出现在原字符串内的索引。支持从指定索引（`fromIndex`）开始搜索。返回值为 `Option<Int64>`，若找到则返回索引，否则返回 `None`。
>
> **3. 比较方法**
> *   **`compare`**: 比较当前字符串与另一个字符串。返回值为 `Ordering` 枚举（如 `LT`, `GT`, `EQ`）。若字符串中存在无效的 UTF-8 编码，会抛出异常。
>
> **4. 修剪方法**
> *   **`trimStart`**: 从头开始修剪字符串，删除符合过滤条件的 `Rune` 字符，直到遇到第一个不符合条件的字符为止。参数可以是过滤函数 `(Rune)->Bool` 或字符集合（`String`/`Array<Rune>`）。
> *   **`trimEnd`**: 从尾开始修剪字符串，删除符合过滤条件的 `Rune` 字符，直到遇到第一个不符合条件的字符为止。参数形式同 `trimStart`。
>
> **5. 转换方法**
> *   **`toUpper`**: 将当前字符串中所有 Unicode …（截断）

#### [stdlib_core_03] ✅ PASS

**问题**：Exception 类和 Error 类的继承关系是怎样的？它们各自的用途是什么？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：69.58% | **关键词覆盖率**：100% | **响应时间**：49.35s
**匹配实体**：`concept:exception`(d=0.315), `concept:_businessexception`(d=0.5534), `concept:processexception`(d=0.5555)
**实体路由命中**：exception, error
**命中关键词**：Exception, Error
**文档目录引用**（7 条）：
  - 「IllegalFormatException」→ ./core_package_api/core_package_exceptions.md
  - 「ProcessException」→ ./process_package_api/process_package_exceptions.md
  - 「ArithmeticException」→ ../../core/core_package_api/core_package_exceptions.md
  - 「Unit」→ ./core_package_api/core_package_intrinsics.md
  - 「CardinalitySelector<A>」→ ./unittest_mock_package_api/unittest_mock_package_classes.md

**回答**：

> 基于提供的图上下文和文档内容，Exception 类和 Error 类的继承关系及用途如下：
>
> **1. 继承关系**
> *   **Exception 类**：继承自 `ToString` 接口（定义：`public open class Exception <: ToString`）。
> *   **Error 类**：继承自 `ToString` 接口（定义：`public open class Error <: ToString`）。
> *   两者在当前上下文中表现为独立的基类，互不直接继承。
>
> **2. 各自用途**
> *   **Exception 类**：
>     *   它是所有异常类的父类。
>     *   用于表示程序运行中可能发生的异常情况。
>     *   支持构造异常实例、设置和获取异常信息、转换为字符串、获取和打印堆栈以及设置异常名等操作。
> *   **Error 类**：
>     *   它是所有错误类的基类。
>     *   用于表示严重的错误情况（如 `StackOverflowError`、`OutOfMemoryError`）。
>     *   根据文档描述，该类不可被继承、不可初始化，但是可以被捕获到。

#### [stdlib_core_04] ✅ PASS

**问题**：Option<T> 类型有什么作用？Some 和 None 构造器如何使用？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：74.54% | **关键词覆盖率**：100% | **响应时间**：28.93s
**匹配实体**：`enum:std_core_option`(d=0.3866), `enum:std_core_option_some`(d=0.4736), `enum:std_core_option_none`(d=0.5023)
**实体路由命中**：option
**命中关键词**：Option, Some, None
**文档目录引用**（1 条）：
  - 「ifSome(Option<T>, (T) -> Unit)」→ ./core_package_api/core_package_funcs.md

**回答**：

> 基于提供的图上下文，`Option<T>` 类型的相关信息如下：
>
> *   **作用**：
>     `Option<T>` 是对类型 `T` 的封装，用于表示一个值可能存在也可能不存在。
>
> *   **构造器使用**：
>     `Option` 包含两个构造器，分别用于表示有值和无值的情况：
>     *   **Some**：用于表示存在值。例如，`Some(200)` 表示封装了一个具体的值（如 `Int64` 类型的 `200`）。
>     *   **None**：用于表示无值。例如，直接使用 `None` 表示没有值。
>
> *   **相关处理**：
>     可以使用 `ifSome` 和 `ifNone` 等函数来分别判断和处理 `Option` 类型的实例是 `Some` 还是 `None`。

#### [stdlib_core_05] ✅ PASS

**问题**：sizeOf<T>() 和 alignOf<T>() 函数的作用是什么？CType 约束是什么含义？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：69.73% | **关键词覆盖率**：100% | **响应时间**：655.46s
**匹配实体**：`concept:alignof`(d=0.4878), `concept:sizeof`(d=0.5099), `function:std_core_sizeof`(d=0.5384)
**实体路由命中**：sizeof, ctype
**命中关键词**：sizeOf, CType
**文档目录引用**（4 条）：
  - 「CType」→ ./core_package_api/core_package_interfaces.md
  - 「ifNone(Option<T>, () -> Unit)」→ ./core_package_api/core_package_funcs.md
  - 「Int8, Int8, Int16」→ ./core_package_api/core_package_intrinsics.md
  - 「max<T>(Iterable<T>) where T <: Comparable<T>」→ ./collection_package_api/collection_package_function.md

**回答**：

> 基于提供的图上下文，以下是关于 `sizeOf<T>()`、`alignOf<T>()` 和 `CType` 约束的说明：
>
> **1. `sizeOf<T>()` 函数**
> *   **作用**：获取类型 `T` 所占用的内存空间大小。
> *   **约束**：类型参数 `T` 必须满足 `CType` 约束（即 `T <: CType`）。
> *   **返回值**：返回 `UIntNative` 类型，表示该类型实例的大小（字节数）。
>
> **2. `alignOf<T>()` 函数**
> *   **定义**：根据上下文，`alignOf<T>()` 是一个泛型函数，其类型参数 `T` 必须满足 `CType` 约束（即 `T <: CType`）。
> *   **说明**：当前提供的上下文中未包含该函数具体功能（如获取对齐值）的详细描述文本，仅列出了其函数签名和约束条件。
>
> **3. `CType` 约束**
> *   **含义**：`CType` 是一个表示支持与 C 语言互操作的接口（sealed interface）。
> *   **实现机制**：
>     *   它是语言内置的空接口，所有 C 互操作支持的类型（如基本数值类型、`@C` 修饰的结构体、`CPointer`、`CString` 等）都**隐式地**实现了该接口。
>     *   因此，这些类型都可以作为满足 `CType` 约束的类型参数使用。
> *   **限制**：
>     *   `CType` 接口本身不满足 `CType` 约束。
>     *   不允许用户继承或扩展该接口。

#### [stdlib_coll_01] ✅ PASS

**问题**：ArrayList 和 LinkedList 的区别是什么？各自适合什么场景？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：74.10% | **关键词覆盖率**：100% | **响应时间**：64.11s
**匹配实体**：`concept:arraylist`(d=0.3467), `concept:list`(d=0.5785), `concept:arraystack`(d=0.584)
**实体路由命中**：arraylist, linkedlist
**命中关键词**：ArrayList, LinkedList
**文档目录引用**（29 条）：
  - 「LinkedListNode<T>」→ ./collection_package_api/collection_package_class.md
  - 「ArrayList」→ ../../collection/collection_package_api/collection_package_class.md
  - 「Array<T>」→ ./core_package_api/core_package_structs.md
  - 「Array<T>」→ ../../core/core_package_api/core_package_structs.md
  - 「any<T>((T) -> Bool)」→ ./collection_package_api/collection_package_function.md

**回答**：

> 基于提供的图上下文和文档内容，ArrayList 和 LinkedList 的区别及适用场景如下：
>
> ### 1. ArrayList
> *   **定义与结构**：
>     *   ArrayList 是一种线性的**动态数组**，实现了 `List<T>` 接口。
>     *   与定长数组 `Array` 不同，它可以根据需要自动调整大小，创建时无需指定大小。
> *   **工作原理**：
>     *   当添加元素时，如果数组已满，会重新分配更大的内存空间，并将原有元素复制到新空间中。
> *   **优缺点**：
>     *   **优点**：节省内存空间，支持自动扩容。
>     *   **缺点**：在重新分配内存空间时可能会导致性能下降。
> *   **适用场景**：
>     *   根据文档描述，它非常适合需要**频繁添加或删除元素**的情况。
>
> ### 2. LinkedList
> *   **定义与结构**：
>     *   LinkedList 基于 `LinkedListNode<T>` 节点构建。
> *   **功能特性**：
>     *   **灵活增删**：支持在头部或尾部添加元素（`addFirst`, `addLast`），也支持在指定节点之前或之后插入元素（`addBefore`, `addAfter`）。
>     *   **双向遍历**：支持从指定标记节点开始向前或向后进行迭代（`forward`, `backward`）。
>     *   **分割操作**：支持从指定节点处将列表拆分（`splitOff`）。
> *   **适用场景**：
>     *   适合需要在**特定节点位置**进行精细的插入或删除操作的场景。
>     *   适合需要**双向遍历**或对列表进行**分割**处理的场景。
>
> ### 3. 主要区别总结
> *   **底层实现**…（截断）

#### [stdlib_coll_02] ✅ PASS

**问题**：如何使用 HashMap 存储键值对并进行查找？HashMap 的底层实现原理是什么？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：39.05% | **关键词覆盖率**：100% | **响应时间**：64.82s
**匹配实体**：`concept:hashmap`(d=0.5864), `class:std_collection_hashmap`(d=0.6185), `codesnippet:hashmap_example`(d=0.6472)
**实体路由命中**：hashmap
**命中关键词**：HashMap, 哈希
**文档目录引用**（7 条）：
  - 「TupleWrapper4」→ ./unittest_prop_test_package_api/unittest_prop_test_package_structs.md
  - 「ArrayDeque, ArrayList, ArrayList」→ ./collection_package_api/collection_package_class.md
  - 「String」→ ./core_package_api/core_package_structs.md
  - 「String」→ ../../core/core_package_api/core_package_structs.md
  - 「ArrayList」→ ../../collection/collection_package_api/collection_package_class.md

**回答**：

> 基于提供的图上下文，关于 HashMap 的使用方法及底层实现原理如下：
>
> ### 如何使用 HashMap 存储键值对并进行查找
>
> 1.  **定义与约束**：
>     *   `HashMap<K, V>` 是 `Map` 接口的实现，用于存储键值对。
>     *   键类型 `K` 必须满足 `Hashable` 和 `Equatable` 约束。
>
> 2.  **初始化与存储**：
>     *   **默认构造**：使用 `init()` 构造一个默认初始容量为 16 的空 HashMap。
>     *   **指定容量**：使用 `init(capacity: Int64)` 指定初始容量。
>     *   **通过集合初始化**：使用 `init(elements: Array<(K, V)>)` 或 `init(elements: Collection<(K, V)>)` 传入键值对集合进行初始化。注意，如果传入的集合中存在重复的键，按照迭代器顺序，后面的键值对会覆盖前面的。
>     *   **函数生成**：可以使用 `collectHashMap` 函数从 `Iterable<(K, V)>` 类型的数据中收集生成 HashMap。
>
> 3.  **查找**：
>     *   `Map` 接口提供了将键映射到值的方式，允许使用键来查找对应的值。
>
> ### HashMap 的底层实现原理
>
> 1.  **数据结构**：
>     *   HashMap 是基于哈希表实现的。
>
> 2.  **核心机制**：
>     *   哈希表将数据映射到一个数组中。
>     *   每个数据元素都有一个对应的哈希值，该哈希值用于确定该元素在数组中的位置。
>
> 3.  **性能与特性**：
>     *   **时间复杂度**：支持快速的查找、插入和删除操作，时间复杂度通常为 O(1)。…（截断）

#### [stdlib_coll_03] ✅ PASS

**问题**：ArrayDeque 双端队列的容量策略是怎样的？初始容量有什么限制？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：70.49% | **关键词覆盖率**：100% | **响应时间**：24.25s
**匹配实体**：`function:std_collection_arraydeque_init_capacity`(d=0.3816), `class:std_collection_arraydeque`(d=0.477), `class:arraydeque`(d=0.5666)
**实体路由命中**：arraydeque, deque
**命中关键词**：ArrayDeque, 容量
**文档目录引用**（1 条）：
  - 「ArrayDeque」→ ./collection_package_api/collection_package_class.md

**回答**：

> 基于提供的图上下文和文档内容，ArrayDeque 双端队列的容量策略及初始容量限制如下：
>
> *   **容量策略**：
>     *   ArrayDeque 基于可调整大小的数组实现。
>     *   在插入元素的过程中，其容量会不断增长，默认每次扩容增加 50% 的大小。
>     *   实现采用了循环队列的方式，在没有扩容的情况下，插入、删除、查看等操作的时间复杂度为 O(1)。
>
> *   **初始容量限制**：
>     *   当使用 `init(capacity: Int64)` 构造函数指定初始容量时，如果指定的 `capacity` 小于默认值 **8**，则实际构造的初始容量将被设置为 8。
>     *   如果指定的 `capacity` 小于 0，将抛出 `IllegalArgumentException` 异常。

#### [stdlib_coll_04] ✅ PASS

**问题**：TreeMap 和 HashMap 的区别是什么？TreeMap 是基于什么数据结构实现的？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：71.41% | **关键词覆盖率**：100% | **响应时间**：97.54s
**匹配实体**：`concept:treemap`(d=0.2437), `concept:treeset`(d=0.4924), `concept:hashmap`(d=0.5257)
**实体路由命中**：treemap, hashmap
**命中关键词**：TreeMap, HashMap
**文档目录引用**（23 条）：
  - 「Array<T>」→ ./core_package_api/core_package_structs.md
  - 「Array<T>」→ ../../core/core_package_api/core_package_structs.md
  - 「ReadOnlySet<K, V>」→ ./collection_package_api/collection_package_interface.md
  - 「LinkedListNode<T>」→ ./collection_package_api/collection_package_class.md
  - 「any<T>((T) -> Bool)」→ ./collection_package_api/collection_package_function.md

**回答**：

> 基于提供的图上下文，相关信息如下：
>
> *   **HashMap**：
>     *   **实现数据结构**：基于**哈希表**实现。
>     *   **基本原理**：将数据映射到一个数组中，每个数据元素通过对应的哈希值确定其在数组中的位置。
>     *   **性能特点**：具有快速的查找、插入和删除操作，时间复杂度通常为 O(1)。
>     *   **顺序性**：由于哈希表底层的数组大小是动态的，因此**不能保证元素的顺序**不可变。
>
> *   **TreeMap**：
>     *   当前图谱信息中仅包含 `TreeMap` 的实体引用，**未提供其具体基于何种数据结构实现的描述**，也未提供其与 HashMap 的详细区别对比。

#### [stdlib_coll_05] ✅ PASS

**问题**：HashSet 和 TreeSet 各自的特点是什么？如何选择使用？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：73.11% | **关键词覆盖率**：100% | **响应时间**：62.8s
**匹配实体**：`concept:hashset`(d=0.2541), `concept:set`(d=0.4658), `concept:collecthashset`(d=0.4843)
**实体路由命中**：hashset, treeset
**命中关键词**：HashSet, TreeSet
**文档目录引用**（24 条）：
  - 「Deque<T>」→ ./collection_package_api/collection_package_interface.md
  - 「Array<T>」→ ./core_package_api/core_package_structs.md
  - 「Array<T>」→ ../../core/core_package_api/core_package_structs.md
  - 「LinkedListNode<T>」→ ./collection_package_api/collection_package_class.md
  - 「any<T>((T) -> Bool)」→ ./collection_package_api/collection_package_function.md

**回答**：

> 基于提供的图上下文，HashSet 和 TreeSet 的特点及选择建议如下：
>
> ### 1. HashSet 的特点
> *   **实现基础**：基于 `HashMap` 实现，实现了 `Set<T>` 接口。
> *   **元素特性**：元素是**无序**的，且不允许有重复元素。
> *   **存储机制**：根据元素的哈希值来确定元素在哈希表中的位置。
> *   **性能与布局**：容量、内存布局、时间性能等与 `HashMap` 相同。
> *   **类型约束**：元素类型 `T` 必须满足 `Hashable` 和 `Equatable<T>`。
> *   **主要属性**：包含 `capacity`（内部数组容量）和 `size`（元素个数）属性。
>
> ### 2. TreeSet 的特点
> *   **类型约束**：根据上下文中的类签名信息，元素类型 `T` 必须满足 `Comparable`。
> *   **集合运算**：支持集合操作，例如使用 `|` 运算符获取与另一个集合的并集，使用 `&` 运算符获取交集。
> *   **克隆操作**：支持 `clone` 方法用于克隆集合。
> *   **注**：当前上下文未提供 TreeSet 关于内部实现（如是否基于 TreeMap）或排序特性的详细描述。
>
> ### 3. 如何选择使用
> *   **选择 HashSet**：当你的元素类型实现了 `Hashable` 和 `Equatable`，且不需要元素保持特定顺序时使用。
> *   **选择 TreeSet**：当你的元素类型实现了 `Comparable`，或者需要进行集合间的并集、交集等运算时使用。

#### [stdlib_math_01] ✅ PASS

**问题**：std.math 包提供了哪些数学函数？包含哪些数学常数？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：76.16% | **关键词覆盖率**：67% | **响应时间**：49.16s
**匹配实体**：`file:__math_math_package_overview_md`(d=0.4756), `module:std_math`(d=0.528), `file:__math_numeric_math_numeric_package_overview_md`(d=0.5642)
**实体路由命中**：math
**命中关键词**：math, abs
**文档目录引用**（2 条）：
  - 「math」→ ./math/math_package_overview.md
  - 「RoundingMode」→ ./math_package_api/math_package_enums.md

**回答**：

> 基于提供的图上下文和文档内容，`std.math` 包提供了以下数学函数和常数：
>
> ### 数学函数
>
> **1. 基础运算函数**
> *   **`abs`**：求绝对值，支持 Float16, Float32, Float64, Int8, Int16, Int32, Int64 类型。
> *   **`pow`**：求幂运算，支持 `pow(Float64, Int64)` 和 `pow(Float64, Float64)` 形式。
> *   **`fmod`**：求两个浮点数相除的余数，支持 Float16, Float32, Float64 类型。
> *   **`gamma`**：求浮点数的伽马函数值。
>
> **2. 三角函数与反三角函数**
> *   **`acos`**：计算浮点数的反余弦函数值。
> *   **`acosh`**：计算浮点数的反双曲余弦函数值。
>
> **3. 数值处理函数**
> *   **`clamp`**：范围截断，将数值限制在指定的最小值和最大值区间内，支持 Float16, Float32, Float64。
> *   **`trunc`**：截断取整，返回浮点数的整数部分，支持 Float16, Float32, Float64。
>
> **4. 整数运算函数**
> *   **`gcd`**：求两个整数的最大公约数，支持 Int8, Int64, UInt8, UInt16, UInt32, UInt64 等多种整数类型。
> *   **`lcm`**：求两个整数的最小公倍数。
> *   **`throwingAdd`**：执行加法运算，如果发生溢出则抛出 `OverflowException`（针对 Int64）。
>
> **5. 位运算函数**
> *   **`rotate`**：按位旋转（循环移位），支持 Int8, Int16, Int32, Int64, …（截断）

#### [stdlib_math_02] ✅ PASS

**问题**：clamp 函数的作用是什么？如何使用它限制浮点数的范围？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：78.46% | **关键词覆盖率**：100% | **响应时间**：39.77s
**匹配实体**：`function:std_math_clamp`(d=0.3643), `codesnippet:std_math_clamp_example`(d=0.4445), `concept:clamp_float32_float32_float32_`(d=0.4792)
**实体路由命中**：clamp
**命中关键词**：clamp
**文档目录引用**（1 条）：
  - 「clamp(Float32, Float32, Float32)」→ ./math_package_api/math_package_funcs.md

**回答**：

> `clamp` 函数的作用及使用方法如下：
>
> **1. 函数作用**
> `clamp` 函数用于将浮点数限制在指定的区间范围内。其具体逻辑为：
> *   如果输入值 `v` 在 `[min, max]` 范围区间内，则返回 `v` 本身；
> *   如果输入值 `v` 小于该范围区间（即小于 `min`），则返回该范围区间的最小值 `min`；
> *   如果输入值 `v` 大于该范围区间（即大于 `max`），则返回该范围区间的最大值 `max`；
> *   如果输入值 `v` 是 `NaN`，则返回 `NaN`。
>
> **2. 如何使用**
> 该函数属于 `std.math` 模块，支持 `Float16`、`Float32` 和 `Float64` 三种浮点类型。
>
> *   **函数签名**：
>     ```cangjie
>     public func clamp(v: Float16, min: Float16, max: Float16): Float16
>     // 同样支持 Float32 和 Float64
>     ```
> *   **参数说明**：
>     *   `v`：需要限制范围的浮点数。
>     *   `min`：允许范围的最小值。
>     *   `max`：允许范围的最大值。
> *   **异常处理**：
>     当参数 `min` 大于参数 `max`，或者 `min` 和 `max` 是 `NaN` 时，会抛出 `IllegalArgumentException`。
>
> **3. 使用示例**
> ```cangjie
> import std.math.clamp
>
> main() {
>     let n: Float16 = -23.0
>     // 将 n 限制在 -100.0 到 100.0 之间
>     let result = clamp(n, -1…（截断）

#### [stdlib_sync_01] ✅ PASS

**问题**：仓颉语言中如何使用 Mutex 互斥锁进行线程同步？synchronized 关键字如何搭配使用？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：34.08% | **关键词覆盖率**：100% | **响应时间**：38.86s
**匹配实体**：`concept:mutex`(d=0.7338), `class:std_sync_mutex`(d=0.8104), `codesnippet:concurrenthashmap_usage_example`(d=0.8386)
**实体路由命中**：mutex, sync
**命中关键词**：Mutex, synchronized
**文档目录引用**（2 条）：
  - 「SynchronizedExpr」→ ./ast_package_api/ast_package_classes.md
  - 「ReadWriteLock」→ ./sync_package_api/sync_package_classes.md

**回答**：

> 基于提供的图上下文，仓颉语言中 `Mutex` 互斥锁与 `synchronized` 关键字的使用方式如下：
>
> ### 1. 使用 Mutex 进行线程同步
> `Mutex` 是一个提供可重入互斥锁功能的类，用于保护临界区，确保任意时刻最多只有一个线程能够执行临界区的代码。
>
> *   **基本操作**：
>     *   **加锁**：在访问共享数据之前，必须调用 `lock()` 函数来获取锁。如果锁已被其他线程持有，当前线程会阻塞。
>     *   **解锁**：处理完共享数据后，必须调用 `unlock()` 函数来释放锁，以便其他线程可以获取。
> *   **特性**：
>     *   **可重入**：线程获取该锁后可以再次获得该锁。
>     *   **非阻塞尝试**：可以使用 `tryLock()` 尝试获取锁而不阻塞线程。
>     *   **条件变量**：可以通过调用 `condition()` 创建一个与该 `Mutex` 关联的 `Condition` 对象，用于实现更复杂的线程等待/通知机制。
>
> ### 2. synchronized 关键字的搭配使用
> `synchronized` 关键字用于构建同步表达式（`SynchronizedExpr`），它提供了一种结构化的加锁方式。
>
> *   **语法结构**：
>     *   表达式由 `synchronized` 关键字、一个 `StructuredMutex` 对象（即锁对象）以及随后的代码块组成。
> *   **使用形式**：
>     *   典型形式为 `synchronized(m) { ... }`。
>     *   其中 `m` 是作为锁的对象（`StructuredMutex`），大括号 `{ ... }` 内的代码块（`Block`）即是被保护的临界区代码。

#### [stdlib_sync_02] ✅ PASS

**问题**：AtomicInt64 原子操作支持哪些方法？compareAndSwap 的行为是怎样的？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：82.56% | **关键词覆盖率**：100% | **响应时间**：47.79s
**匹配实体**：`concept:atomicint64`(d=0.2335), `concept:atomicuint64`(d=0.4303), `class:atomicint64`(d=0.4844)
**实体路由命中**：atomicint64, atomic
**命中关键词**：AtomicInt64, 原子
**文档目录引用**（6 条）：
  - 「ReentrantWriteMutex <sup>(deprecated)</sup>」→ ./sync_package_api/sync_package_classes.md
  - 「UInt64」→ ./core_package_api/core_package_intrinsics.md
  - 「UInt64」→ ../../core/core_package_api/core_package_intrinsics.md
  - 「Option<T>」→ ./core_package_api/core_package_enums.md
  - 「Option<T>」→ ../core/core_package_api/core_package_enums.md

**回答**：

> 基于提供的图上下文，`AtomicInt64` 支持的原子操作方法及 `compareAndSwap` 的行为如下：
>
> ### 支持的原子操作方法
>
> `AtomicInt64` 提供了以下几类原子操作方法（多数方法支持通过 `MemoryOrder` 参数指定内存排序方式）：
>
> 1.  **初始化**
>     *   `init(val: Int64)`: 使用给定的初始值创建原子整数。
>
> 2.  **读取与存储**
>     *   `load()`: 原子读取当前值。
>     *   `load(memoryOrder: MemoryOrder)`: 指定内存排序方式，原子读取当前值。
>     *   `store(val: Int64)`: 原子存储新值，替换当前值。
>     *   `store(val: Int64, memoryOrder: MemoryOrder)`: 指定内存排序方式，原子存储新值。
>
> 3.  **交换**
>     *   `swap(val: Int64)`: 原子地将当前值与给定值交换，返回旧值。
>     *   `swap(val: Int64, memoryOrder: MemoryOrder)`: 指定内存排序方式，原子交换并返回旧值。
>
> 4.  **比较并交换 (CAS)**
>     *   `compareAndSwap(old: Int64, new: Int64)`: 原子比较并交换。
>     *   `compareAndSwap(old: Int64, new: Int64, successOrder: MemoryOrder, failureOrder: MemoryOrder)`: 指定成功和失败时的内存排序方式，原子比较并交换。
>
> 5.  **算术运算 (Fetch-and-Add/Sub)**
>     *   `f…（截断）

#### [stdlib_time_01] ✅ PASS

**问题**：DateTime 类型如何解析时间字符串？支持哪些格式化模式？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：74.85% | **关键词覆盖率**：100% | **响应时间**：53.49s
**匹配实体**：`function:std_time_datetime_parse`(d=0.4687), `concept:时间字符串格式`(d=0.469), `function:std_time_datetime_format`(d=0.5641)
**实体路由命中**：datetime
**命中关键词**：DateTime, 格式
**文档目录引用**（2 条）：
  - 「DateTime」→ ./time_package_api/time_package_structs.md
  - 「时间字符串格式」→ ../time_package_overview.md

**回答**：

> 基于提供的图上下文，DateTime 类型解析时间字符串及支持的格式化模式如下：
>
> ### 1. 如何解析时间字符串
> 使用 `DateTime` 类的静态函数 `DateTime.parse` 进行解析。
> *   **函数**：`DateTime.parse(str, pattern)`
> *   **参数**：
>     *   `str`：待解析的时间字符串。
>     *   `pattern`：指定的格式化字符串（由格式化字母组成）。
> *   **解析规则**：
>     *   **必须包含日期信息**：字符串必须包含公元年（`y`）+ 月（`M`）+ 日（`d`），或者公元年（`y`）+ 一年中的第几天（`D`）。
>     *   **默认值**：如果不包含时分秒信息，默认为 0；如果不包含时区信息，默认为当前时区（`TimeZone.Local`）。
>     *   **唯一性限制**：同一格式字母不允许重复赋值（例如不允许出现两次 `y`）；时区格式 `O` 和 `Z` 不允许同时出现。
>     *   **辅助验证**：其余部分字母作为辅助信息验证（例如验证星期几是否与日期匹配）。
>
> ### 2. 支持的格式化模式（字母含义）
> 格式化字符串由以下字母组合而成：
>
> | 字母 | 含义 |
> | :--- | :--- |
> | **y** | 公元年 |
> | **Y** | 基于周的年 |
> | **M** | 月份 |
> | **d** | 日（月份中的天数） |
> | **D** | 以年算的天数 |
> | **w** | 以周算的天 |
> | **W** | 基于 ISO-8601 标准的周 |
> | **H** | 24 小时制的小时 |
> | **h** | 12 小时制的小时 |
> | **m** | 分钟数 |
> | **s** | 秒数 |
> | **S** | 小于一秒的…（截断）

#### [stdlib_time_02] ✅ PASS

**问题**：Duration 和 TimeZone 类型各自的作用是什么？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：76.48% | **关键词覆盖率**：100% | **响应时间**：30.53s
**匹配实体**：`concept:duration`(d=0.3037), `concept:duration_max`(d=0.4065), `concept:keyminduration`(d=0.4385)
**实体路由命中**：duration, timezone
**命中关键词**：Duration, TimeZone
**文档目录引用**（18 条）：
  - 「KeyMinDuration」→ ./unittest_package_api/unittest_package_structs.md
  - 「DateTimeFormat, DateTimeFormat, TimeZone」→ ./time_package_api/time_package_classes.md
  - 「Array<T>, Array<T>, CPointerHandle<T> where T <: CType」→ ./core_package_api/core_package_structs.md
  - 「Array<T>」→ ../../core/core_package_api/core_package_structs.md
  - 「CString」→ ./core_package_api/core_package_intrinsics.md

**回答**：

> 基于提供的图上下文，Duration 和 TimeZone 类型的作用如下：
>
> **1. Duration**
> *   **作用**：表示时间间隔，是一个描述一段时间的时间类型。
> *   **功能**：
>     *   提供了常用的静态实例，如 `nanosecond`（纳秒）、`millisecond`（毫秒）、`second`（秒）、`minute`（分）、`hour`（小时）、`day`（天）等。
>     *   支持计算、比较（实现 `Comparable` 接口）以及转换为字符串（实现 `ToString` 接口）。
>     *   数值表示范围为 $[-2^{63}, 2^{63})$ 秒，精度为纳秒。
> *   **应用场景**：常用于需要指定时间长度的操作，例如 `sleep`（休眠）、`once`（延迟执行任务）、`remove`（超时等待）等函数的参数。
>
> **2. TimeZone**
> *   **作用**：表示时区，记录了某一地区在不同时间较零时区（UTC）的时间偏移。
> *   **功能**：
>     *   提供了静态实例 `Local`（本地时区）和 `UTC`（协调世界时）。
>     *   支持通过 `load` 静态函数根据字符串 ID（如 `Asia/Shanghai`）从系统加载时区信息。
>     *   支持通过构造函数自定义时区（指定 ID 和偏移量）。
>     *   提供获取时区 ID 的属性 `id` 和字符串表示方法 `toString`。
> *   **应用场景**：主要用于 `DateTime` 的处理，例如在创建 `DateTime` 实例时指定时区，或通过 `inTimeZone` 方法将当前时间转换为指定时区的时间。

#### [stdlib_io_01] ✅ PASS

**问题**：BufferedInputStream 的作用是什么？它和 InputStream 接口是什么关系？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：74.59% | **关键词覆盖率**：100% | **响应时间**：28.66s
**匹配实体**：`concept:bufferedinputstream`(d=0.3784), `class:bufferedinputstream`(d=0.3977), `class:std_io_bufferedinputstream`(d=0.4395)
**实体路由命中**：bufferedinputstream, inputstream
**命中关键词**：BufferedInputStream, InputStream
**文档目录引用**（4 条）：
  - 「BufferedInputStream<T> where T <: InputStream」→ ./io_package_api/io_package_classes.md
  - 「Array<T>」→ ./core_package_api/core_package_structs.md
  - 「Array<T>」→ ../../core/core_package_api/core_package_structs.md
  - 「IOStream」→ ./io_package_api/io_package_interfaces.md

**回答**：

> **BufferedInputStream 的作用**
>
> *   **提供带缓冲区的输入流**：它通过内部缓冲区来优化读取操作。
> *   **数据暂存机制**：可以将其他 `InputStream` 类型的输入流（如 `ByteBuffer`）绑定到 `BufferedInputStream` 实例。从该实例读取数据时，先把数据从被绑定的流读入缓冲区暂存，再从缓冲区读取用户需要的数据。
> *   **配置灵活**：支持使用默认缓冲区容量（4096 字节）、指定容量或自定义缓冲区数组来初始化。
>
> **与 InputStream 接口的关系**
>
> *   **继承关系**：`BufferedInputStream` 继承自 `InputStream` 接口（定义为 `public class BufferedInputStream<T> <: InputStream`）。
> *   **泛型约束**：它是一个泛型类，其类型参数 `T` 必须是 `InputStream` 的子类型（即 `where T <: InputStream`），意味着它可以包装任何实现了 `InputStream` 的流。

#### [stdlib_io_02] ✅ PASS

**问题**：ByteBuffer 如何使用？它在 IO 操作中扮演什么角色？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：41.98% | **关键词覆盖率**：100% | **响应时间**：53.49s
**匹配实体**：`class:std_io_bytebuffer`(d=0.616), `codesnippet:bytebuffer_example`(d=0.6512), `concept:bytebuffer`(d=0.674)
**实体路由命中**：bytebuffer
**命中关键词**：ByteBuffer
**文档目录引用**（1 条）：
  - 「ByteBuffer」→ ./io_package_api/io_package_classes.md

**回答**：

> ByteBuffer 是 `std.io` 模块中用于对流进行写入数据、读取数据等操作的缓冲区类。它实现了 `IOStream` 和 `Seekable` 接口。
>
> **使用方式：**
> *   **创建实例**：使用 `init()` 创建，默认初始容量为 32。
> *   **写入数据**：调用 `write(buffer: Array<Byte>)` 向缓冲区写入数据。
> *   **读取数据**：调用 `read(buffer: Array<Byte>)` 从输入流中读取数据到指定数组。
> *   **位置控制**：调用 `seek(sp: SeekPosition)` 移动流的索引位置（光标）。
> *   **缓冲区管理**：
>     *   `clear()`：清除缓冲区中的所有数据。
>     *   `reserve(size)`：将缓冲区扩容指定大小。
>     *   `clone()`：用当前数据构造一个新的 ByteBuffer。
>     *   `bytes()`：获取当前未被读取的数据切片。
>
> **在 IO 操作中的角色：**
> *   **基础流**：作为内存中的缓冲区，直接支持数据的读写和随机访问。
> *   **缓冲流的底层源/目标**：可以被绑定到 `BufferedInputStream` 或 `BufferedOutputStream` 实例中，作为带缓冲输入/输出流的数据源或输出目标。
> *   **其他流的输出目标**：可作为 `StringWriter` 或 `MultiOutputStream` 的输出流，用于接收转换后的字符串或同时写入多个流。

#### [stdlib_regex_01] ✅ PASS

**问题**：仓颉语言中如何使用 Regex 进行正则表达式匹配？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：40.46% | **关键词覆盖率**：100% | **响应时间**：50.66s
**匹配实体**：`module:std_regex`(d=0.6724), `file:__regex_regex_package_overview_md`(d=0.7218), `class:std_regex_regex`(d=0.7868)
**实体路由命中**：regex
**命中关键词**：Regex, 正则
**文档目录引用**（3 条）：
  - 「Matcher <sup>(deprecated)</sup>, regex, regex」→ ./regex_package_api/regex_package_classes.md
  - 「regex, regex」→ ./regex/regex_package_overview.md
  - 「MatchData」→ ./regex_package_api/regex_package_structs.md

**回答**：

> 在仓颉语言中，使用 `std.regex` 模块进行正则表达式匹配主要涉及创建 `Regex` 对象、调用匹配方法以及处理 `MatchData` 结果。以下是具体的使用方式：
>
> ### 1. 引入模块
> 在使用正则功能前，需要先引入标准库的正则模块：
> ```cangjie
> import std.regex.*
> ```
>
> ### 2. 创建正则对象
> 使用 `Regex` 类的构造函数创建实例，可以指定模式字符串和匹配选项（如忽略大小写、多行模式等）。
>
> *   **基本构造**：
>     ```cangjie
>     let r = Regex("ab")
>     ```
> *   **带选项构造**（例如忽略大小写）：
>     ```cangjie
>     let r = Regex("ab", IgnoreCase)
>     ```
>     支持的选项包括 `IgnoreCase`（忽略大小写）、`MultiLine`（多行匹配）、`Unicode`（Unicode 匹配）等。
>
> ### 3. 执行匹配操作
> `Regex` 类提供了多种方法来执行不同类型的匹配：
>
> *   **`matches(input: String)`**：判断输入字符串是否**整体**匹配正则表达式，返回 `Bool`。
>     ```cangjie
>     let r = Regex(#"\d{4}-\d{2}-\d{2}"#)
>     let isMatch = r.matches("2024-10-24") // 返回 true
>     ```
>
> *   **`find(input: String, group!: Bool)`**：查找输入字符串中**第一个**匹配的子序列。返回 `Option<MatchData>`，匹配成功返回 `Some`，否则返回 `None`。
>     ```ca…（截断）

#### [stdlib_misc_01] ✅ PASS

**问题**：IncompatiblePackageException 在什么场景下会被抛出？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：78.13% | **关键词覆盖率**：100% | **响应时间**：29.54s
**匹配实体**：`concept:incompatiblepackageexception`(d=0.3038), `class:incompatiblepackageexception`(d=0.3705), `function:incompatiblepackageexception_init_string_`(d=0.5657)
**实体路由命中**：incompatiblepackageexception
**命中关键词**：IncompatiblePackageException
**文档目录引用**（2 条）：
  - 「IllegalFormatException」→ ./core_package_api/core_package_exceptions.md
  - 「IllegalMemoryException」→ ../../core/core_package_api/core_package_exceptions.md

**回答**：

> 根据提供的图谱上下文，`IncompatiblePackageException` 在以下场景下会被使用：
>
> *   **包不兼容**：该异常类专门用于表示**包不兼容**的情况。
>
> 此外，上下文还提供了该异常类的以下技术细节：
> *   **继承关系**：它继承自 `Exception` 类。
> *   **构造方式**：支持两种构造方式，一种是默认构造（异常信息为空），另一种是接受 `String` 类型参数以指定异常提示信息。
>
> （注：当前上下文未列出具体抛出该异常的函数或操作流程。）

#### [sdk_arkui_01] ✅ PASS

**问题**：List 组件如何设置滚动方向？listDirection 方法如何使用？
**数据源**：interface_sdk_cangjie | **搜索模式**：local
**置信度**：72.77% | **关键词覆盖率**：100% | **响应时间**：32.17s
**匹配实体**：`concept:listattribute`(d=0.4383), `concept:importlist`(d=0.5094), `concept:list`(d=0.5428)
**实体路由命中**：list
**命中关键词**：List, Direction
**文档目录引用**（7 条）：
  - 「List<T>」→ ./collection_package_api/collection_package_interface.md
  - 「MemberAccess」→ ./ast_package_api/ast_package_classes.md
  - 「Annotation」→ ./reflect_package_api/reflect_package_types.md
  - 「Unit」→ ./core_package_api/core_package_intrinsics.md
  - 「Option<T>」→ ./core_package_api/core_package_enums.md

**回答**：

> 基于提供的图谱上下文，List 组件设置滚动方向及 `listDirection` 方法的使用方式如下：
>
> *   **设置方法**：通过调用 `listDirection` 方法来设置 List 组件的滚动方向。
> *   **方法签名**：`public func listDirection(value: ?Axis): This`
> *   **参数说明**：
>     *   该方法接受一个名为 `value` 的参数，其类型为 `?Axis`。
> *   **返回值**：方法返回 `This`，表明该方法支持链式调用。
> *   **关联实体**：该方法属于 `ListAttribute`（List 属性）的一部分。
>
> （注：当前上下文中未包含 `Axis` 类型的具体枚举值定义，因此无法提供具体的方向选项，如垂直或水平。）

#### [sdk_arkui_02] ✅ PASS

**问题**：Row 组件如何设置子元素的垂直对齐和水平分布？alignItems 和 justifyContent 如何使用？
**数据源**：interface_sdk_cangjie | **搜索模式**：local
**置信度**：38.68% | **关键词覆盖率**：100% | **响应时间**：34.91s
**匹配实体**：`concept:duration_max`(d=0.5415), `concept:requiredvalue`(d=0.5988), `concept:funcs`(d=0.6107)
**实体路由命中**：row
**命中关键词**：Row, alignItems
**文档目录引用**（25 条）：
  - 「Array<T>」→ ./core_package_api/core_package_structs.md
  - 「Array<T>」→ ../../core/core_package_api/core_package_structs.md
  - 「OptionalValue」→ ./argopt_package_enums.md
  - 「ArgumentSpec」→ ./argopt_package_api/argopt_package_enums.md
  - 「LinkedListNode<T>」→ ./collection_package_api/collection_package_class.md

**回答**：

> 基于提供的图上下文，Row 组件设置子元素垂直对齐和水平分布的方法如下：
>
> *   **设置子元素的垂直对齐**
>     *   使用 `alignItems` 方法。
>     *   **参数**：接受一个 `VerticalAlign` 类型的值。
>     *   **作用**：用于设置子组件在垂直方向上的对齐方式。
>
> *   **设置子元素的水平分布**
>     *   使用 `justifyContent` 方法。
>     *   **参数**：接受一个 `FlexAlign` 类型的值。
>     *   **作用**：用于设置子组件在水平方向上的对齐（分布）方式。
>
> 这两个方法均返回 Row 实例本身，支持链式调用。

#### [sdk_interop_01] ✅ PASS

**问题**：JSArrayBuffer 类提供了哪些方法来读取和转换字节数据？
**数据源**：interface_sdk_cangjie | **搜索模式**：local
**置信度**：38.20% | **关键词覆盖率**：100% | **响应时间**：33.6s
**匹配实体**：`function:toarraybufferjsvalue`(d=0.6433), `class:jsarraybuffer`(d=0.7673), `struct:stdx_core_array`(d=0.7715)
**实体路由命中**：jsarraybuffer
**命中关键词**：JSArrayBuffer, readBytes

**回答**：

> 基于图上下文中的 `JSArrayBuffer` 类定义，该类提供了以下方法来读取和转换字节数据：
>
> **1. 读取为 Cangjie 数组**
> 这些方法将绑定内存读取并转换为 Cangjie 的原生数组类型：
> *   `readBytes()`: 读取为 `Array<Byte>`。
> *   `toUInt8Array()`: 读取为 `Array<UInt8>`。
> *   `toInt8Array()`: 读取为 `Array<Int8>`。
> *   `toUInt16Array()`: 读取为 `Array<UInt16>`。
> *   `toInt16Array()`: 读取为 `Array<Int16>`。
> *   `toInt32Array()`: 读取为 `Array<Int32>`。
> *   `toUInt32Array()`: 读取为 `Array<UInt32>`。
> *   `toFloat32Array()`: 读取为 `Array<Float32>`。
> *   `toUInt64Array()`: 读取为 `Array<UInt64>`。
> *   `toInt64Array()`: 读取为 `Array<Int64>`。
> *   `toFloat64Array()`: 读取为 `Array<Float64>`。
>
> **2. 转换为 ArkTS JSValue**
> 这些方法将绑定内存转换为 ArkTS 中的 TypedArray 或 ArrayBuffer 对象，返回 `JSValue` 类型：
> *   `toArrayBufferJSValue()`: 转换为 ArkTS 的 `ArrayBuffer`。
> *   `toUInt8ArrayJSValue()`: 转换为 ArkTS 的 `Uint8Array`。
> *   `toUInt8Clamped…（截断）

#### [regression_01] ✅ PASS

**问题**：LinkedList在仓颉语言中有什么作用？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：37.38% | **关键词覆盖率**：100% | **响应时间**：35.64s
**匹配实体**：`concept:linkedlist`(d=0.7661), `class:std_collection_linkedlist`(d=0.7775), `concept:list`(d=0.7927)
**实体路由命中**：linkedlist
**命中关键词**：LinkedList
**文档目录引用**（7 条）：
  - 「Array<T>」→ ./core_package_api/core_package_structs.md
  - 「Array<T>」→ ../../core/core_package_api/core_package_structs.md
  - 「ArrayDeque, ArrayList, ArrayList」→ ./collection_package_api/collection_package_class.md
  - 「Unit」→ ./core_package_api/core_package_intrinsics.md
  - 「ArrayList」→ ../../collection/collection_package_api/collection_package_class.md

**回答**：

> 基于提供的图谱上下文，LinkedList 在仓颉语言中的作用主要体现在以下几个方面：
>
> *   **实现双向链表数据结构**：它用于实现一种由一系列节点组成的线性集合，每个节点包含两个指针，分别指向前一个节点和后一个节点。
> *   **支持双向遍历**：得益于双向指针的结构，LinkedList 允许从任意节点进行双向遍历，既可以从头节点开始向后遍历，也可以从尾节点开始向前遍历。
> *   **集合接口实现**：它实现了 `Collection<T>` 接口，并扩展了 `Equatable` 和 `ToString` 接口（在满足特定泛型约束时）。
> *   **迭代器失效特性**：该结构不支持并发操作。在对集合中元素进行修改时，通常不会使迭代器失效，但在执行添加和删除元素的操作时，会使迭代器失效。
> *   **节点管理**：配合 `LinkedListNode` 类，支持在链表头部（`addFirst`）或指定节点后（`addAfter`）插入元素等操作。

#### [regression_02] ✅ PASS

**问题**：IncompatiblePackageException是什么？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：75.92% | **关键词覆盖率**：100% | **响应时间**：22.15s
**匹配实体**：`concept:incompatiblepackageexception`(d=0.2373), `class:incompatiblepackageexception`(d=0.3135), `exception:std_core_unsupportedexception`(d=0.5056)
**实体路由命中**：incompatiblepackageexception
**命中关键词**：IncompatiblePackageException
**文档目录引用**（2 条）：
  - 「IllegalFormatException」→ ./core_package_api/core_package_exceptions.md
  - 「ArithmeticException」→ ../../core/core_package_api/core_package_exceptions.md

**回答**：

> IncompatiblePackageException 是一个表示包不兼容的异常类。
>
> - **继承关系**：继承自 `Exception` 类。
> - **构造方法**：
>     - `init()`：构造一个默认的实例，默认异常信息为空。
>     - `init(message: String)`：根据指定的异常提示信息构造一个实例。

#### [regression_03] ✅ PASS

**问题**：HashSet有什么性质？
**数据源**：Cangjie_StdLib | **搜索模式**：local
**置信度**：70.81% | **关键词覆盖率**：100% | **响应时间**：24.86s
**匹配实体**：`concept:hashset`(d=0.4607), `class:stdx_collection_hashset`(d=0.5738), `concept:set`(d=0.6037)
**实体路由命中**：hashset
**命中关键词**：HashSet
**文档目录引用**（12 条）：
  - 「Array<T>」→ ./core_package_api/core_package_structs.md
  - 「Array<T>」→ ../../core/core_package_api/core_package_structs.md
  - 「ReadOnlySet<K, V>」→ ./collection_package_api/collection_package_interface.md
  - 「ArrayDeque, ArrayList, ArrayList」→ ./collection_package_api/collection_package_class.md
  - 「Unit」→ ./core_package_api/core_package_intrinsics.md

**回答**：

> 基于提供的图上下文，HashSet 具有以下性质：
>
> 1.  **无序性与唯一性**：HashSet 中的元素是无序的，且不允许有重复元素。
> 2.  **基于 HashMap 实现**：它是基于 HashMap 实现的 Set 接口的实例。因此，其容量、内存布局和时间性能等特性与 HashMap 相同。
> 3.  **哈希定位**：当向 HashSet 中添加元素时，会根据元素的哈希值来确定该元素在哈希表中的位置。
> 4.  **类型约束**：泛型类型参数 `T` 必须满足 `Hashable`（可哈希）和 `Equatable`（可判等）接口。
> 5.  **接口实现**：除了继承自 `Set<T>` 接口外，还实现了 `Equatable<HashSet<T>>` 和 `ToString` 接口。
> 6.  **容量与大小**：拥有 `capacity` 属性（表示内部数组容量大小）和 `size` 属性（表示元素个数），两者不一定相等。

#### [global_01] ✅ PASS

**问题**：请总结仓颉语言标准库的整体模块架构设计，包括 core、collection、math、sync、time、io 等包的分工。
**数据源**：all | **搜索模式**：global
**置信度**：50.00% | **关键词覆盖率**：100% | **响应时间**：393.23s
**命中关键词**：标准库, 模块, core

**回答**：

> 基于仓颉语言标准库的技术社区摘要，以下是对其整体模块架构设计的体系化总结。该架构旨在为系统级编程提供安全、高效且高并发的基础设施，涵盖了从底层数值操作到上层业务逻辑支持的完整技术栈。
>
> ### 仓颉语言标准库整体模块架构设计
>
> 仓颉标准库的架构设计遵循模块化与层次化原则，旨在提供类型安全、内存安全以及高性能的运行时支持。整体架构划分为六大核心模块，各模块分工明确且紧密协作。
>
> #### 1. Core（核心基础模块）
> **设计定位**：作为整个标准库的基石，提供语言运行时的核心抽象、基础类型系统及异常处理机制。
>
> *   **基础类型与数值策略**：构建了安全且可控的数值系统。针对原生类型（如 Int64、UInt64），不仅提供基础运算，还实现了多种溢出处理策略（如 `saturating` 饱和运算、`checked` 检查运算、`wrapping` 回绕运算），以满足底层开发对确定性和安全性的严苛要求。
> *   **异常与反射体系**：建立了统一的异常处理基类（`Exception`），并集成了强大的反射机制。通过 `TypeInfo` 和 `FunctionInfo` 等实体，支持运行时类型检查、子类型判断及元编程，为框架层提供动态能力。
> *   **容器抽象**：提供了基础容器类型，如 `Option`，用于更优雅地处理空值安全，增强代码的健壮性。
>
> #### 2. Collection（集合框架模块）
> **设计定位**：提供功能完备、类型安全且支持高并发场景的数据结构集合。
>
> *   **基础数据结构**：实现了链表、有序映射、树集等常用线性与非线性数据结构，支持通用集合算法。
> *   **并发集合**：针对高并发场景进行了专门优化，提供了如 `ConcurrentHashMap` 和 `LinkedBlockingQueue` 等线程安全的集合组件。这些组件内…（截断）

#### [global_02] ✅ PASS

**问题**：仓颉语言的核心包（std.core）包含哪些关键类和接口？它们如何支撑整个标准库体系？
**数据源**：all | **搜索模式**：local
**置信度**：37.74% | **关键词覆盖率**：100% | **响应时间**：62.2s
**匹配实体**：`class:std_array`(d=0.7783), `struct:std_core_libc`(d=0.797), `module:mypackage`(d=0.8606)
**命中关键词**：core, 类, 接口
**文档目录引用**（3 条）：
  - 「core」→ ./core/core_package_overview.md
  - 「Unit」→ ./core_package_api/core_package_intrinsics.md
  - 「LibC」→ ./core_package_api/core_package_structs.md

**回答**：

> 基于提供的图上下文和文档，仓颉语言的核心包（`std.core`）包含以下关键类、接口及基础类型，它们通过提供基础数据结构、通用行为约束和系统交互能力，支撑了整个标准库体系：
>
> ### 一、 关键类和接口
>
> **1. 基础接口**
> *   **`ToString`**：定义类型转换为字符串的能力，被 `String`、`Int64`、`Float64`、`Array`、`HashMap` 等绝大多数核心及集合类型实现，用于统一输出和调试。
> *   **`Equatable`**：定义相等性比较（`==` 和 `!=`）的能力，支持基本数值类型、`String`、`Array`、`Option` 等类型的判等操作。
> *   **`Hashable`**：定义计算哈希值的能力，是 `HashMap` 和 `HashSet` 等哈希集合正常工作的基础，被 `String`、`Int64`、`Rune`、`Path` 等实现。
> *   **`Collection`**：定义集合的通用行为，被 `Array`、`String`、`LinkedList` 等实现，支持统一的迭代和元素访问。
> *   **`CType`**：用于与 C 语言交互的接口约束，不允许用户继承，用于标记可与 C 指针互操作的类型（如 `Int64`、`UInt8` 等）。
>
> **2. 核心类**
> *   **`StringBuilder`**：用于高效构建字符串，性能优于直接使用 `String` 连接。
> *   **`Exception` 及其子类（如 `IllegalArgumentException`）**：作为所有异常类的基类，提供异常信息设置、堆栈获取和打印等功能，支撑标准库的错误处理机制。
> *   **`Iterator`**：提供 `next` 方法，支持对容器（如 `Array`、`HashMa…（截断）


### 4.2 文档目录引用（DOCUMENTED_AT）利用统计

在 31 个局部搜索测试中，30 个获取到了文档目录引用。

| 测试ID | 文档引用数 | 示例引用 |
|--------|-----------|---------|
| stdlib_core_01 | 2 | 「Float64」→ ./core_package_api/core_package_intrinsics.md |
| stdlib_core_02 | 7 | 「String」→ ./core_package_api/core_package_structs.md |
| stdlib_core_03 | 7 | 「IllegalFormatException」→ ./core_package_api/core_package_exceptions.md |
| stdlib_core_04 | 1 | 「ifSome(Option<T>, (T) -> Unit)」→ ./core_package_api/core_package_funcs.md |
| stdlib_core_05 | 4 | 「CType」→ ./core_package_api/core_package_interfaces.md |
| stdlib_coll_01 | 29 | 「LinkedListNode<T>」→ ./collection_package_api/collection_package_class.md |
| stdlib_coll_02 | 7 | 「TupleWrapper4」→ ./unittest_prop_test_package_api/unittest_prop_test_package_structs.md |
| stdlib_coll_03 | 1 | 「ArrayDeque」→ ./collection_package_api/collection_package_class.md |
| stdlib_coll_04 | 23 | 「Array<T>」→ ./core_package_api/core_package_structs.md |
| stdlib_coll_05 | 24 | 「Deque<T>」→ ./collection_package_api/collection_package_interface.md |
| stdlib_math_01 | 2 | 「math」→ ./math/math_package_overview.md |
| stdlib_math_02 | 1 | 「clamp(Float32, Float32, Float32)」→ ./math_package_api/math_package_funcs.md |
| stdlib_sync_01 | 2 | 「SynchronizedExpr」→ ./ast_package_api/ast_package_classes.md |
| stdlib_sync_02 | 6 | 「ReentrantWriteMutex <sup>(deprecated)</sup>」→ ./sync_package_api/sync_package_classes.md |
| stdlib_time_01 | 2 | 「DateTime」→ ./time_package_api/time_package_structs.md |
| stdlib_time_02 | 18 | 「KeyMinDuration」→ ./unittest_package_api/unittest_package_structs.md |
| stdlib_io_01 | 4 | 「BufferedInputStream<T> where T <: InputStream」→ ./io_package_api/io_package_classes.md |
| stdlib_io_02 | 1 | 「ByteBuffer」→ ./io_package_api/io_package_classes.md |
| stdlib_regex_01 | 3 | 「Matcher <sup>(deprecated)</sup>, regex, regex」→ ./regex_package_api/regex_package_classes.md |
| stdlib_misc_01 | 2 | 「IllegalFormatException」→ ./core_package_api/core_package_exceptions.md |
| sdk_arkui_01 | 22 | 「Bench」→ ./unittest_testmacro_package_api/unittest_testmacro_package_macros.md |
| sdk_arkui_02 | 5 | 「Array<T>, Array<T>, CPointerHandle<T> where T <: CType」→ ./core_package_api/core_package_structs.md |
| sdk_arkui_03 | 23 | 「Array<T>」→ ./core_package_api/core_package_structs.md |
| sdk_arkui_04 | 7 | 「List<T>」→ ./collection_package_api/collection_package_interface.md |
| sdk_arkui_05 | 25 | 「Array<T>」→ ./core_package_api/core_package_structs.md |
| regression_01 | 7 | 「Array<T>」→ ./core_package_api/core_package_structs.md |
| regression_02 | 2 | 「IllegalFormatException」→ ./core_package_api/core_package_exceptions.md |
| regression_03 | 12 | 「Array<T>」→ ./core_package_api/core_package_structs.md |
| global_02 | 3 | 「core」→ ./core/core_package_overview.md |
| global_03 | 19 | 「findProcess」→ ./process_package_api/process_package_funcs.md |

## 5. 搜索优化策略总结（含文档目录引用增强）

本次对 `search_engine.py`、`test_search_report.py` 进行了以下优化：

| 优化点 | 实现方式 | 预期效果 |
|--------|----------|----------|
| 多候选实体检索 | `_vector_route_intent_multi(top_k=3)` | 避免只取 top-1 时遗漏相关实体，提升召回率 |
| 多实体子图融合 | `_collect_multi_entity_subgraph` | 合并多个候选实体的 1~2 跳邻居，丰富上下文 |
| 相似度 × 中心性重排序 | 综合得分 = sim_score × (1 + degree_centrality) | 让最相关且图中最重要的实体优先被 LLM 看到 |
| 置信度评分 | `_compute_confidence`（相似度+高置信奖励+子图密度） | 为答案提供可解释的置信度指标 |
| 上下文节点数量控制 | `max_nodes=80` 截断策略 | 防止 context 过长超出 LLM 窗口，保留高分节点 |
| 关键词回退检索 | `_keyword_fallback_candidates`：名称命中权重3，内容命中权重1 | 向量索引不可用时自动降级，保证本地搜索不会空返回 |
| **文档目录引用增强（新增）** | `_collect_doc_directory_info`：遍历 DOCUMENTED_AT 关系 | 在搜索结果中附带关联文档路径，LLM 可参考原始文档丰富回答 |
| **补充文档内容加载（新增）** | `_load_supplementary_content`：从 temp_repos 加载关联文档原文 | 当图谱信息不足时，自动补充来自原始文档的详细内容 |
| **SearchResult.doc_references（新增）** | 返回结果携带 `doc_references` 字段 | 下游（如 serve.py）可展示文档溯源链接，增强可追溯性 |
