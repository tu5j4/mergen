#![no_std]

use core::{ffi::c_void, panic::PanicInfo, ptr, slice};

#[panic_handler]
fn panic(_: &PanicInfo) -> ! {
    // No unwinding across a foreign-language boundary.
    unsafe { core::arch::asm!("ud2", options(noreturn)) }
}

#[no_mangle]
pub static _fltused: i32 = 0;

#[no_mangle]
pub unsafe extern "C" fn memcpy(dest: *mut c_void, source: *const c_void, count: usize) -> *mut c_void {
    for i in 0..count { ptr::write_volatile(dest.cast::<u8>().add(i), ptr::read_volatile(source.cast::<u8>().add(i))); }
    dest
}

#[no_mangle]
pub unsafe extern "C" fn memset(dest: *mut c_void, value: i32, count: usize) -> *mut c_void {
    for i in 0..count { ptr::write_volatile(dest.cast::<u8>().add(i), value as u8); }
    dest
}

#[no_mangle]
pub unsafe extern "C" fn memcmp(a: *const c_void, b: *const c_void, count: usize) -> i32 {
    for i in 0..count {
        let x=ptr::read_volatile(a.cast::<u8>().add(i));let y=ptr::read_volatile(b.cast::<u8>().add(i));
        if x!=y { return x as i32-y as i32; }
    }
    0
}

#[no_mangle]
pub unsafe extern "C" fn memmove(dest: *mut c_void, source: *const c_void, count: usize) -> *mut c_void {
    if (dest as usize) > source as usize {
        for i in (0..count).rev() { ptr::write_volatile(dest.cast::<u8>().add(i),ptr::read_volatile(source.cast::<u8>().add(i))); }
        dest
    } else { memcpy(dest,source,count) }
}

#[repr(C)]
pub struct BoxData { x1: f64, y1: f64, x2: f64, y2: f64, bubble: i32, panel: i32 }

#[repr(C)]
pub struct Rect { x: f64, y: f64, w: f64, h: f64 }

#[no_mangle]
pub extern "C" fn mergen_geometry_abi() -> u32 { 1 }

#[no_mangle]
pub extern "C" fn mergen_geometry_sizes() -> u64 {
    ((core::mem::size_of::<BoxData>() as u64) << 32) | core::mem::size_of::<Rect>() as u64
}

fn root(parents: &mut [u32], mut i: usize) -> usize {
    while parents[i] as usize != i {
        parents[i] = parents[parents[i] as usize];
        i = parents[i] as usize;
    }
    i
}

fn join(parents: &mut [u32], i: usize, j: usize) {
    let a = root(parents, i); let b = root(parents, j);
    if a != b { parents[b] = a as u32; }
}

// SAFETY: caller supplies aligned disjoint buffers of length n, valid until return.
#[no_mangle]
pub unsafe extern "C" fn mergen_group_boxes(boxes: *const BoxData, n: usize,
        gap_ratio: f64, same_bubble_gap: f64, flags: u32, output: *mut u32) -> i32 {
    if n == 0 { return 0; }
    if n > 8192 || boxes.is_null() || output.is_null() { return -1; }
    let boxes = slice::from_raw_parts(boxes, n);
    let parents = slice::from_raw_parts_mut(output, n);
    for (i, value) in parents.iter_mut().enumerate() { *value = i as u32; }
    for i in 0..n {
        let a = &boxes[i];
        let aw = (a.x2-a.x1).max(1.); let ah = (a.y2-a.y1).max(1.);
        let av = ah > aw * 1.5; let ahorizontal = aw > ah * 1.5;
        let ca = aw.min(ah);
        for j in i+1..n {
            let b = &boxes[j];
            if flags & 2 != 0 && a.panel != b.panel { continue; }
            if flags & 1 != 0 && a.bubble != b.bubble { continue; }
            let bw = (b.x2-b.x1).max(1.); let bh = (b.y2-b.y1).max(1.);
            let bv = bh > bw * 1.5; let bhorizontal = bw > bh * 1.5;
            if (av && bhorizontal) || (bv && ahorizontal) { continue; }
            let cb = bw.min(bh);
            if ca.max(cb) / ca.min(cb).max(1.) > 2.2 { continue; }
            let known_same = flags & 1 != 0 && a.bubble >= 0 && a.bubble == b.bubble;
            if av && bv && ah.max(bh) / ah.min(bh).max(1.) > 2.7
                    && !(flags & 8 != 0 && known_same) { continue; }
            let gap = ca.max(cb) * gap_ratio;
            let hgap = (a.x1.max(b.x1)-a.x2.min(b.x2)).max(0.);
            let vgap = (a.y1.max(b.y1)-a.y2.min(b.y2)).max(0.);
            let xo = (a.x2.min(b.x2)-a.x1.max(b.x1)).max(0.) / aw.min(bw).max(1.);
            let yo = (a.y2.min(b.y2)-a.y1.max(b.y1)).max(0.) / ah.min(bh).max(1.);
            if flags & 4 != 0 && flags & 1 != 0 && a.bubble >= 0
                    && ahorizontal && bhorizontal && xo > 0.65
                    && vgap <= ca.max(cb) * same_bubble_gap { join(parents, i, j); }
            let side_overlap = if av && bv { 0.6 } else { 0.3 };
            if (yo > side_overlap && hgap <= gap) || (xo > 0.3 && vgap <= gap) { join(parents, i, j); }
        }
    }
    for i in 0..n { parents[i] = root(parents, i) as u32; }
    0
}

// SAFETY: caller supplies aligned input buffers and output capacity >= n.
#[no_mangle]
pub unsafe extern "C" fn mergen_overlap_indices(query: *const Rect, rectangles: *const Rect,
        n: usize, output: *mut u32, capacity: usize) -> i32 {
    if n == 0 { return 0; }
    if n > 8192 || capacity < n || query.is_null() || rectangles.is_null() || output.is_null() { return -1; }
    let q = &*query;
    let mut count = 0;
    for (i, r) in slice::from_raw_parts(rectangles, n).iter().enumerate() {
        let ix = ((q.x+q.w).min(r.x+r.w)-q.x.max(r.x)).max(0.);
        let iy = ((q.y+q.h).min(r.y+r.h)-q.y.max(r.y)).max(0.);
        if ix * iy / (q.w*q.h).min(r.w*r.h).max(1.) > 0.5 {
            *output.add(count) = i as u32; count += 1;
        }
    }
    count as i32
}
