"""NuitkaShield v9.0 — Layer 4: True Dispatch Table CFF (AI-Resistant)"""
from __future__ import annotations
import ast, hashlib, os, random
from typing import List, Dict, Any

_DEAD_STATE = 0xDEAD_C0DE

def _make_state(seed: int, idx: int) -> int:
    h = hashlib.sha256(f"{seed}:{idx}:{os.urandom(4).hex()}".encode()).digest()
    val = int.from_bytes(h[:4], "big") & 0x7FFFFFFF
    return val if val != _DEAD_STATE else val ^ 0xABCD1234

def _is_sensitive(name: str) -> bool:
    kw = {"verify","token","license","hwid","auth","secret","key","decrypt","encrypt","guard","check","validate","safe","secure","credential","hash","sign","admin","root","pipeline","manager"}
    return any(k in name.lower() for k in kw)

class CFFEngine(ast.NodeTransformer):
    def __init__(self, seed: int | None = None):
        self._seed = seed or int.from_bytes(os.urandom(4), "big")
        self._state_funcs: List[ast.FunctionDef] = []
        self._state_ids: List[int] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.generic_visit(node)
        if _is_sensitive(node.name) and len(node.body) >= 2:
            return self._transform_to_cff(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """
        Bảo vệ các hàm async def (để tránh lỗi C1001 của MSVC).
        Chỉ quét các node con bên trong chứ TUYỆT ĐỐI KHÔNG gọi _transform_to_cff.
        """
        self.generic_visit(node)
        return node

    def _transform_to_cff(self, func: ast.FunctionDef) -> ast.FunctionDef:
        stmts = func.body
        n = len(stmts)

        S_VAR = "_𝔖"
        R_VAR = "_𝔔"

        # === 1. BỘ ĐÁNH CHẶN RETURN SỚM (ANTI-INFINITE LOOP) ===
        class ReturnFixer(ast.NodeTransformer):
            def visit_Return(self, node):
                # Thay lệnh "return X" bằng 3 lệnh:
                # 1. _Q = X
                # 2. _S = _DEAD_STATE
                # 3. return None (để thoát khỏi hàm _st_ hiện tại một cách an toàn)
                return [
                    ast.Assign(targets=[ast.Name(id=R_VAR, ctx=ast.Store())], value=node.value or ast.Constant(None)),
                    ast.Assign(targets=[ast.Name(id=S_VAR, ctx=ast.Store())], value=ast.Constant(_DEAD_STATE)),
                    ast.Return(value=None)
                ]

        # === 1. TÌM TẤT CẢ CÁC BIẾN CỤC BỘ CỦA HÀM GỐC ===
        # === 1. TÌM TẤT CẢ CÁC BIẾN (BAO GỒM CẢ HÀM LỒNG) ===
        local_vars = set()
        class VarFinder(ast.NodeVisitor):
            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Store):
                    local_vars.add(node.id)
                self.generic_visit(node)
            
            def visit_FunctionDef(self, node):
                # Bắt tên của hàm lồng (như hàm emit)
                local_vars.add(node.name)
                # Không đi sâu vào bên trong hàm con để tránh rối loạn biến của nó
                pass 
            
            def visit_AsyncFunctionDef(self, node):
                local_vars.add(node.name)
                pass

        for s in stmts:
            VarFinder().visit(s)
        
        # Lọc bỏ các biến hệ thống của CFF
        local_vars = [v for v in local_vars if v not in (S_VAR, R_VAR, "_𝔇", "_hdl")]
        # ================================================

        # Generate state IDs cryptographic
        states = [_make_state(self._seed, i) for i in range(n)]
        next_states = [states[i+1] if i+1 < n else _DEAD_STATE for i in range(n)]

        S_VAR = "_𝔖"  # State variable
        R_VAR = "_𝔔"  # Return value variable

        self._state_funcs = []
        self._state_ids = states

        # Build state handlers
        # Build state handlers
        for i, (stmt, st, nxt) in enumerate(zip(stmts, states, next_states)):
            
            # === 2. ĐƯA TẤT CẢ BIẾN VÀO NONLOCAL ===
            nonlocal_names = [S_VAR, R_VAR] + local_vars
            handler_body: List[ast.stmt] = [
                ast.Nonlocal(names=nonlocal_names)
            ] if nonlocal_names else []

            # === 3. XỬ LÝ STATEMENT (ĐÃ FIX RETURN & FUNCTION SCOPE) ===
            # Sử dụng ReturnFixer để biến "return X" thành "nhảy về DEAD_STATE"
            fixed_stmt = ReturnFixer().visit(stmt)
            
            if isinstance(fixed_stmt, list):
                handler_body.extend(fixed_stmt)
            elif isinstance(fixed_stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Giữ nguyên định nghĩa hàm lồng để nó gán vào scope cha
                handler_body.append(fixed_stmt)
            else:
                handler_body.append(fixed_stmt)

            # === 4. NHẢY TRẠNG THÁI (XOR) ===
            # Chỉ nhảy trạng thái nếu statement hiện tại không phải là Return 
            # (Vì Return đã có logic nhảy về DEAD_STATE riêng ở ReturnFixer)
            if not isinstance(stmt, ast.Return):
                xor_key = st ^ nxt
                mutation = ast.Assign(
                    targets=[ast.Name(id=S_VAR, ctx=ast.Store())],
                    value=ast.BinOp(
                        left=ast.Name(id=S_VAR, ctx=ast.Load()),
                        op=ast.BitXor(),
                        right=ast.Constant(xor_key)
                    )
                )
                handler_body.append(mutation)

            # Add junk dead branch (runtime-dependent, always False)
            # Add junk dead branch (runtime-dependent, always False)
            # if i % 2 == 0:
            #     junk_cond = ast.Compare(
            #         left=ast.Call(
            #             func=ast.Name(id="id", ctx=ast.Load()),
            #             args=[ast.Name(id="object", ctx=ast.Load())],
            #             keywords=[]
            #         ),
            #         ops=[ast.Eq()],
            #         comparators=[ast.Constant(value=id(object))]
            #     )
                
            #     # BẮT BUỘC SỬA THÀNH ĐOẠN NÀY (Dùng ast.Raise thay vì ast.Expr + exit)
            #     junk_if = ast.If(
            #         test=junk_cond,
            #         body=[ast.Raise(exc=ast.Call(func=ast.Name(id="SystemExit", ctx=ast.Load()), args=[ast.Constant(1)], keywords=[]), cause=None)],
            #         orelse=[]
            #     )
                
            #     handler_body.append(junk_if)

            # Create state handler function
            handler = ast.FunctionDef(
                name=f"_st_{st}",
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg="_s", annotation=None)],
                    kwonlyargs=[],
                    kw_defaults=[],
                    defaults=[]
                ),
                body=handler_body,
                decorator_list=[],
                returns=None
            )
            self._state_funcs.append(handler)

        # Build dispatch table: {state_id: handler_func}
        dispatch_dict = ast.Dict(
            keys=[ast.Constant(s) for s in states],
            values=[ast.Name(id=f"_st_{s}", ctx=ast.Load()) for s in states]
        )

        # Build while dispatcher loop
        dispatcher_loop = ast.While(
            test=ast.Compare(
                left=ast.Name(id=S_VAR, ctx=ast.Load()),
                ops=[ast.NotEq()],
                comparators=[ast.Constant(_DEAD_STATE)]
            ),
            body=[
                ast.Assign(
                    targets=[ast.Name(id="_hdl", ctx=ast.Store())],
                    value=ast.Subscript(
                        value=ast.Name(id="_𝔇", ctx=ast.Load()),
                        slice=ast.Name(id=S_VAR, ctx=ast.Load()),
                        ctx=ast.Load()
                    )
                ),
                ast.Expr(
                    value=ast.Call(
                        func=ast.Name(id="_hdl", ctx=ast.Load()),
                        args=[ast.Name(id=S_VAR, ctx=ast.Load())],
                        keywords=[]
                    )
                )
            ],
            orelse=[]
        )

        # Rebuild function body
        # Rebuild function body
        # === 3. KHỞI TẠO TẤT CẢ BIẾN BẰNG NONE ===
        init_locals = [
            ast.Assign(targets=[ast.Name(id=v, ctx=ast.Store())], value=ast.Constant(None))
            for v in local_vars
        ]

        # Rebuild function body
        func.body = [
            # Khởi tạo biến trạng thái
            ast.Assign(targets=[ast.Name(id=S_VAR, ctx=ast.Store())], value=ast.Constant(states[0] if states else _DEAD_STATE)),
            # Khởi tạo biến return
            ast.Assign(targets=[ast.Name(id=R_VAR, ctx=ast.Store())], value=ast.Constant(None))
        ] + init_locals + self._state_funcs + [  # <--- CHÈN INIT_LOCALS VÀO ĐÂY
            # Build dispatch table
            ast.Assign(targets=[ast.Name(id="_𝔇", ctx=ast.Store())], value=dispatch_dict),
            # Run dispatcher
            dispatcher_loop,
            # Return stored value
            ast.Return(value=ast.Name(id=R_VAR, ctx=ast.Load()))
        ]

        return func